# apps/match/views.py
import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.sql import func
from sqlalchemy.orm import aliased  # Import aliased function

# apps.extensions에서 db를 가져옵니다.
from apps.extensions import db

from apps.match.forms import LogSearchForm, MatchSearchForm, NewMatchForm
from ..dbmodels import MatchLog, MatchLogType, User, Match, MatchStatus, UserType
from apps.decorators import admin_required  # 데코레이터

from . import match  # Blueprint 정의

"""
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # 행위자(admin)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # 일반 사용자
    expert_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # 전문가
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))  # 매칭 대상

def log_action(title, summary, target_user_id=None, status_code=200):
    #관리자 행동을 로그로 기록하는 헬퍼 함수
    try:
        new_log = MatchLog(
            user_id=current_user.id,
            target_user_id=target_user_id,
            endpoint=request.path,
            log_title=title,
            log_summary=summary,
            remote_addr=request.remote_addr,
            response_status_code=status_code,
        )
        db.session.add(new_log)
    except Exception as e:
        # 로깅 실패가 주 작업에 영향을 주지 않도록 처리
        print(f"로깅 실패: {e}")
"""

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
    
    # '매칭 관리' 탭에서 사용할 전문가 드롭다운 목록
    match_search_form.expert_id.choices = [(0, '전체 전문가')] + [(expert.id, expert.username) for expert in experts]

    # '신규 매칭' 탭 로직 (검색)
    new_match_query = User.query.filter(User.user_type == UserType.USER, User.match_status == MatchStatus.UNASSIGNED)
    if request.method == 'POST' and 'search_submit' in request.form:
        if new_match_form.validate_on_submit():
            email_query = new_match_form.email.data
            start_date_query = new_match_form.start_date.data
            end_date_query = new_match_form.end_date.data

            if email_query:
                new_match_query = new_match_query.filter(User.email.ilike(f'%{email_query}%'))
            if start_date_query:
                new_match_query = new_match_query.filter(User.created_at >= start_date_query)
            if end_date_query:
                new_match_query = new_match_query.filter(User.created_at <= end_date_query + datetime.timedelta(days=1))
    
    users_to_match = new_match_query.order_by(User.created_at.desc()).all()

    # '매칭 관리' 탭 로직 (검색 및 페이지네이션)
    page = request.args.get('page', 1, type=int)
    
    # SQLAlchemy의 aliased 함수를 사용하여 User 테이블에 대한 별칭(alias) 생성
    expert_alias = aliased(User)
    
    # 두 번째 outerjoin에 aliased 객체 사용
    matches_query = db.session.query(Match).join(User, Match.user_id == User.id).outerjoin(expert_alias, Match.expert_id == expert_alias.id)
    print(matches_query)    
    # filtered_args 딕셔너리 초기화
    filtered_args = {}

    # GET 요청의 URL 파라미터로 검색 조건 반영
    user_id_query = request.args.get('user_id', type=int)
    expert_id_query = request.args.get('expert_id', type=int)
    status_query = request.args.get('status', 'all', type=str)
    start_date_query = request.args.get('start_date', type=datetime.date.fromisoformat if request.args.get('start_date') else None)
    end_date_query = request.args.get('end_date', type=datetime.date.fromisoformat if request.args.get('end_date') else None)
    
    # 필터 적용
    if user_id_query:
        matches_query = matches_query.filter(Match.user_id == user_id_query)
        filtered_args['user_id'] = user_id_query
    if expert_id_query and expert_id_query != 0:
        matches_query = matches_query.filter(Match.expert_id == expert_id_query)
        filtered_args['expert_id'] = expert_id_query
    if status_query and status_query != 'all':
        matches_query = matches_query.filter(Match.status == MatchStatus(status_query))
        filtered_args['status'] = status_query
    if start_date_query:
        matches_query = matches_query.filter(Match.created_at >= start_date_query)
        filtered_args['start_date'] = start_date_query.isoformat()
    if end_date_query:
        matches_query = matches_query.filter(Match.created_at <= end_date_query + datetime.timedelta(days=1))
        filtered_args['end_date'] = end_date_query.isoformat()

    pagination = matches_query.order_by(Match.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    matches_history = pagination.items
    print(matches_history)
    # 탭별 항목 수 계산
    unassigned_matches_count = User.query.filter_by(match_status=MatchStatus.UNASSIGNED, user_type=UserType.USER).count()
    completed_matches_count = Match.query.filter(Match.status.in_([MatchStatus.IN_PROGRESS, MatchStatus.COMPLETED])).count()

    return render_template(
        'match/match_manager.html',
        new_match_form=new_match_form,
        match_search_form=match_search_form,
        users_to_match=users_to_match,
        matches_history=matches_history,
        pagination=pagination,
        unassigned_matches_count=unassigned_matches_count,
        completed_matches_count=completed_matches_count,
        filtered_args=filtered_args,
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
                        print(f'("user_id",user_id)')
                        match_log = MatchLog(
                            admin_id=current_user.id,
                            user_id=user_id,
                            expert_id=expert_id,
                            match_id=new_match.id,
                            match_status=MatchStatus.IN_PROGRESS,
                            log_title=MatchLogType.MATCH_CREATE.value,
                            log_summary=f"신규 매칭 생성: 사용자({user_id}) - 전문가({expert_id})"
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
                #print("match_to_update1")
                #print(match_to_update)
                #print("match_to_update2")
                #print(match_to_update.user_id)
                if match_to_update and match_to_update.status == MatchStatus.IN_PROGRESS:
                    original_expert_id = match_to_update.expert_id
                    match_to_update.expert_id = new_expert_id
                    print(match_to_update.user_id)
                    #print(match_to_update.user_id.username)
                    username = match_to_update.user.username
                    print(username)  
                    match_log = MatchLog(
                        admin_id=current_user.id,
                        user_id=match_to_update.user_id,
                        expert_id=new_expert_id,
                        match_id=match_id,
                        match_status=MatchStatus.IN_PROGRESS,
                        log_title=MatchLogType.MATCH_EXPERT_CHANGE.value,
                        log_summary=f"매칭 전문가 변경: 기존({original_expert_id}) -> 신규({new_expert_id})"
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
                        log_title=MatchLogType.MATCH_ERASE.value,
                        log_summary=f"매치 취소 처리: 매칭 ID {match_id}",
                    )
                    db.session.add(match_log)
                    cancelled_count += 1
            db.session.commit()
            flash(f"총 {cancelled_count}건의 매칭이 취소되었습니다.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"작업 처리 중 오류가 발생했습니다: {str(e)}", "danger")

    return redirect(url_for('match.match_manager'))

import csv
from datetime import datetime, time
from io import StringIO
from flask import render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from sqlalchemy import or_, cast, String
from sqlalchemy.orm import joinedload

from apps.extensions import db
from apps.match.forms import AdminLogSearchForm
from ..dbmodels import MatchLog, MatchLogType, User, Match, MatchStatus
from apps.decorators import admin_required

from . import match

@match.route('/logs', methods=['GET', 'POST'])
@login_required
@admin_required
def log_list():
    """매칭 로그를 검색하고 목록을 보여주는 페이지"""
    PER_PAGE = 10
    
    form = AdminLogSearchForm()
    
    # 기본 쿼리: MatchLog와 관련된 사용자 정보를 모두 join
    logs_query = MatchLog.query.options(
        joinedload(MatchLog.admin),
        joinedload(MatchLog.user),
        joinedload(MatchLog.expert)
    )
    
    filtered_args = {}

    if form.validate_on_submit():
        # POST 요청: 폼 데이터를 처리하고 GET 요청으로 리디렉션 (PRG 패턴)
        filtered_args['keyword'] = form.keyword.data if form.keyword.data else ''
        filtered_args['log_title'] = form.log_title.data if form.log_title.data else ''
        filtered_args['start_date'] = form.start_date.data.isoformat() if form.start_date.data else ''
        filtered_args['end_date'] = form.end_date.data.isoformat() if form.end_date.data else ''
        return redirect(url_for('match.log_list', **filtered_args))
    
    elif request.method == 'GET':
        # GET 요청: URL의 쿼리 파라미터로 폼을 채움
        form = AdminLogSearchForm(request.args)
    
    # GET 또는 POST 리디렉션 후 필터링 로직
    # 폼 데이터가 유효한 경우에만 필터링을 적용
    if form.keyword.data:
        keyword = f"%{form.keyword.data}%"
        logs_query = logs_query.filter(
            or_(
                cast(MatchLog.user_id, String).ilike(keyword),
                cast(MatchLog.expert_id, String).ilike(keyword),
                MatchLog.log_title.ilike(keyword),
                MatchLog.log_summary.ilike(keyword)
            )
        )
        filtered_args['keyword'] = form.keyword.data

    if form.log_title.data:
        logs_query = logs_query.filter(MatchLog.log_title == form.log_title.data)
        filtered_args['log_title'] = form.log_title.data
    
    if form.start_date.data:
        start_of_day = datetime.combine(form.start_date.data, time.min)
        logs_query = logs_query.filter(MatchLog.timestamp >= start_of_day)
        filtered_args['start_date'] = form.start_date.data.isoformat()
        
    if form.end_date.data:
        end_of_day = datetime.combine(form.end_date.data, time.max)
        logs_query = logs_query.filter(MatchLog.timestamp <= end_of_day)
        filtered_args['end_date'] = form.end_date.data.isoformat()
    
    page = request.args.get('page', 1, type=int)
    logs_pagination = logs_query.order_by(MatchLog.timestamp.desc()).paginate(
        page=page, 
        per_page=PER_PAGE, 
        error_out=False
    )
    
    return render_template(
        'match/logs.html',
        title='매칭 로그 조회',
        form=form,
        logs=logs_pagination.items,
        pagination=logs_pagination,
        filtered_args=filtered_args,
    )

@match.route('/logs/download-csv')
@login_required
@admin_required
def logs_download_csv():
    """필터링된 매칭 로그를 CSV 파일로 다운로드합니다."""
    # GET 요청의 쿼리 파라미터로 필터링 조건을 가져옴
    form = AdminLogSearchForm(request.args)
    
    logs_query = MatchLog.query.options(
        joinedload(MatchLog.admin),
        joinedload(MatchLog.user),
        joinedload(MatchLog.expert)
    )

    if form.keyword.data:
        keyword = f"%{form.keyword.data}%"
        logs_query = logs_query.filter(
            or_(
                cast(MatchLog.user_id, String).ilike(keyword),
                cast(MatchLog.expert_id, String).ilike(keyword),
                MatchLog.log_title.ilike(keyword),
                MatchLog.log_summary.ilike(keyword)
            )
        )

    if form.log_title.data:
        logs_query = logs_query.filter(MatchLog.log_title == form.log_title.data)
    
    if form.start_date.data:
        start_of_day = datetime.combine(form.start_date.data, time.min)
        logs_query = logs_query.filter(MatchLog.timestamp >= start_of_day)
        
    if form.end_date.data:
        end_of_day = datetime.combine(form.end_date.data, time.max)
        logs_query = logs_query.filter(MatchLog.timestamp <= end_of_day)
    
    logs = logs_query.order_by(MatchLog.timestamp.desc()).all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    # CSV 헤더 작성
    headers = [
        "ID", "행위자(Admin ID)", "대상 사용자(User ID)", "대상 전문가(Expert ID)",
        "매치 ID", "로그 제목", "내용 요약", "타임스탬프"
    ]
    writer.writerow(headers)
    
    # 로그 데이터 작성
    for log in logs:
        row = [
            log.id,
            log.admin_id,
            log.user_id,
            log.expert_id,
            log.match_id,
            log.log_title,
            log.log_summary,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ]
        writer.writerow(row)
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=match_logs.csv"}
    )