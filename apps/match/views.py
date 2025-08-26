# apps/match/views.py
import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.sql import func

# apps.extensions에서 db를 가져옵니다.
from apps.extensions import db

from apps.match.forms import MatchSearchForm, NewMatchForm
from ..dbmodels import MatchLog, User, Match, MatchStatus, UserType
from apps.decorators import admin_required  # 데코레이터

from . import match  # Blueprint 정의

@match.route('/', methods=['GET', 'POST'], strict_slashes=False)
@login_required
@admin_required
def match_manager():
    new_match_form = NewMatchForm()
    match_search_form = MatchSearchForm()

    # 전문가 목록을 폼에 채우기
    experts = User.query.filter_by(user_type=UserType.EXPERT, is_active=True, is_deleted=False).order_by(User.username).all()
    expert_choices = [(expert.id, expert.username) for expert in experts]

    if not expert_choices:
        expert_choices = [(0, '--- 선택 가능한 전문가가 없습니다 ---')]
    
    expert_choices.insert(0, (0, '--- 전문가 선택 ---'))
    new_match_form.expert_id.choices = expert_choices
    match_search_form.batch_expert_id.choices = expert_choices
    match_search_form.expert_id.choices = expert_choices

    # '신규 매칭' 탭 로직
    query = User.query.filter(User.user_type == UserType.USER, User.match_status == MatchStatus.UNASSIGNED)
    if request.method == 'POST' and 'new_match_search_submit' in request.form:
        email_query = new_match_form.email.data
        start_date_query = new_match_form.start_date.data
        end_date_query = new_match_form.end_date.data

        if email_query:
            query = query.filter(User.email.ilike(f'%{email_query}%'))
        if start_date_query:
            query = query.filter(User.created_at >= start_date_query)
        if end_date_query:
            query = query.filter(User.created_at <= end_date_query + datetime.timedelta(days=1))

    users_to_match = query.order_by(User.created_at.desc()).all()

    # '매칭 관리' 탭 로직
    page = request.args.get('page', 1, type=int)
    matches_query = Match.query.order_by(Match.created_at.desc())

    if request.method == 'POST' and 'match_history_search_submit' in request.form:
        user_id_query = match_search_form.user_id.data
        expert_id_query = match_search_form.expert_id.data
        status_query = match_search_form.status.data
        start_date_query = match_search_form.start_date.data
        end_date_query = match_search_form.end_date.data

        if user_id_query:
            matches_query = matches_query.filter(Match.user_id == user_id_query)
        if expert_id_query:
            matches_query = matches_query.filter(Match.expert_id == expert_id_query)
        if status_query != 'all':
            matches_query = matches_query.filter(Match.status == MatchStatus(status_query))
        if start_date_query:
            matches_query = matches_query.filter(Match.created_at >= start_date_query)
        if end_date_query:
            matches_query = matches_query.filter(Match.created_at <= end_date_query + datetime.timedelta(days=1))

    pagination = matches_query.paginate(page=page, per_page=10, error_out=False)
    matches_history = pagination.items

    return render_template(
        'match/match_manager.html',
        new_match_form=new_match_form,
        match_search_form=match_search_form,
        users_to_match=users_to_match,
        matches_history=matches_history,
        pagination=pagination
    )


@match.route('/new', methods=['POST'])
@login_required
@admin_required
def create_new_match():
    new_match_form = NewMatchForm()

    # 전문가 목록 채우기
    experts = User.query.filter_by(user_type=UserType.EXPERT, is_active=True, is_deleted=False).order_by(User.username).all()
    expert_choices = [(expert.id, expert.username) for expert in experts]

    if not expert_choices:
        expert_choices = [(0, '--- 선택 가능한 전문가가 없습니다 ---')]

    expert_choices.insert(0, (0, '--- 전문가 선택 ---'))
    new_match_form.expert_id.choices = expert_choices

    if new_match_form.validate_on_submit():
        user_ids = request.form.getlist('user_ids')     # 
        expert_id = new_match_form.expert_id.data

        if not user_ids or expert_id == 0:
            flash("사용자 또는 전문가를 선택해야 합니다.", "danger")
        else:
            new_matches_created = []
            try:
                for user_id in user_ids:
                    user_to_match = User.query.get(user_id)
                    if user_to_match and user_to_match.match_status == MatchStatus.UNASSIGNED:
                        new_match = Match(user_id=user_id, expert_id=expert_id, status=MatchStatus.IN_PROGRESS)
                        db.session.add(new_match)
                        
                        db.session.flush()

                        user_to_match.match_status = MatchStatus.IN_PROGRESS

                        match_log = MatchLog(
                            admin_id=current_user.id,
                            user_id=user_id,
                            expert_id=expert_id,
                            match_id=new_match.id,
                            match_status=MatchStatus.IN_PROGRESS,
                            action_summary=f"신규 매칭 생성: 사용자({user_id}) - 전문가({expert_id})"
                        )
                        db.session.add(match_log)
                        new_matches_created.append(user_id)
                    else:
                        flash(f"사용자 ID {user_id}는 이미 매칭 상태이거나 존재하지 않습니다.", "warning")
            
                db.session.commit()
                flash(f"총 {len(new_matches_created)}건의 새로운 매칭이 생성되었습니다.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"매칭 생성 중 오류가 발생했습니다: {str(e)}", "danger")

    return redirect(url_for('match.match_manager'))


# 수정된 batch_update_matches 함수
@match.route('/batch_update', methods=['POST'])
@login_required
@admin_required
def batch_update_matches():
    # 전문가 목록 받아오기 및 choices 준비
    experts = User.query.filter_by(user_type=UserType.EXPERT, is_active=True, is_deleted=False).order_by(User.username).all()
    expert_choices = [(expert.id, expert.username) for expert in experts]
    if not expert_choices:
        expert_choices = [(0, '--- 선택 가능한 전문가가 없습니다 ---')]
    batch_expert_choices = [(0, '--- 전문가 선택 ---')] + expert_choices

    # 폼 인스턴스를 request.form으로 생성
    match_search_form = MatchSearchForm(request.form)

    # 반드시 동적으로 status와 기타 SelectField의 choices 할당!
    match_search_form.status.choices = [('all', '모두')] + [(s.name, s.value) for s in MatchStatus]
    match_search_form.batch_expert_id.choices = batch_expert_choices

    # 폼에서 status가 빠져 있으면 기본값 할당   (핵심!)
    if 'status' not in request.form:
        match_search_form.status.data = 'all'
        
    # 매칭 선택(match_ids) 필드 값을 기반으로 choices 동적 세팅
    match_ids_str = request.form.getlist('match_ids')
    match_ids = [int(id_str) for id_str in match_ids_str if id_str.isdigit()]
    match_search_form.match_ids.choices = [(int(id), id) for id in match_ids_str]

    # ------ 일괄 할당 처리 ------
    if 'batch_assign_submit' in request.form:
        if not match_ids:
            flash("매칭을 하나 이상 선택해야 합니다.", "danger")
            return redirect(url_for('match.match_manager'))

        if not match_search_form.validate_on_submit():
            # 폼 에러 메시지 한글로 치환
            for field, errors in match_search_form.errors.items():
                for error in errors:
                    # 영어 오류 메시지 한글로 변환
                    if error == "Not a valid choice.":
                        error = "유효하지 않은 선택입니다."
                    flash(f"{match_search_form[field].label.text}: {error}", "danger")
            return redirect(url_for('match.match_manager'))

        try:
            new_expert_id = match_search_form.batch_expert_id.data
            updated_count = 0
            for match_id in match_ids:
                match_to_update = Match.query.get(match_id)
                if match_to_update and match_to_update.status == MatchStatus.IN_PROGRESS:
                    original_expert_id = match_to_update.expert_id
                    match_to_update.expert_id = new_expert_id

                    match_log = MatchLog(
                        admin_id=current_user.id,
                        match_id=match_id,
                        match_status=MatchStatus.IN_PROGRESS,
                        action_summary=f"매칭 전문가 변경: 기존({original_expert_id}) -> 신규({new_expert_id})"
                    )
                    db.session.add(match_log)
                    updated_count += 1
            db.session.commit()
            flash(f"총 {updated_count}건의 매칭에 전문가를 재할당했습니다.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"작업 처리 중 오류가 발생했습니다: {str(e)}", "danger")

    # ------ 일괄 취소 처리 ------
    elif 'batch_cancel_submit' in request.form:
        if not match_ids:
            flash("매칭을 하나 이상 선택해야 합니다.", "danger")
            return redirect(url_for('match.match_manager'))

        try:
            cancelled_count = 0
            for match_id in match_ids:
                match_to_cancel = Match.query.get(match_id)
                if match_to_cancel and match_to_cancel.status != MatchStatus.CANCELLED:
                    match_to_cancel.status = MatchStatus.CANCELLED
                    match_to_cancel.closed_at = datetime.datetime.now()
                    user = User.query.get(match_to_cancel.user_id)
                    if user:
                        user.match_status = MatchStatus.UNASSIGNED
                    match_log = MatchLog(
                        admin_id=current_user.id,
                        match_id=match_id,
                        match_status=MatchStatus.CANCELLED,
                        action_summary=f"매칭 취소 처리: 매칭 ID {match_id}"
                    )
                    db.session.add(match_log)
                    cancelled_count += 1
            db.session.commit()
            flash(f"총 {cancelled_count}건의 매칭이 취소되었습니다.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"작업 처리 중 오류가 발생했습니다: {str(e)}", "danger")

    return redirect(url_for('match.match_manager'))