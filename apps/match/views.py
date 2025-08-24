# apps/match/views.py
import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.sql import func
from functools import wraps
from ..dbmodels import MatchLog, db, User, Match, MatchStatus, UserType

# apps/decorators.py 모듈이 따로 있을 경우 가져옴.
from apps.decorators import admin_required

# apps/match/__init__.py 에서 정의한 blueprint 객체를 가져옴
from . import match

@match.route('/')
@match.route('/manage', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_matches():
    page = request.args.get('page', 1, type=int)
    per_page = 10 # 페이지당 항목 수

    # 검색 폼 데이터
    user_id_keyword = request.args.get('user_id_keyword', '', type=str)
    expert_id_keyword = request.args.get('expert_id_keyword', '', type=str)
    status_filter = request.args.get('status_filter', '', type=str)
    start_date_str = request.args.get('start_date', '', type=str)
    end_date_str = request.args.get('end_date', '', type=str)

    query = Match.query.join(User, Match.user_id == User.id)

    # 검색 조건 적용
    if user_id_keyword:
        query = query.filter(User.email.ilike(f'%{user_id_keyword}%') | (User.id == user_id_keyword))
    
    if expert_id_keyword:
        expert_alias = db.aliased(User)
        query = query.join(expert_alias, Match.expert_id == expert_alias.id)
        query = query.filter(expert_alias.email.ilike(f'%{expert_id_keyword}%') | (expert_alias.id == expert_id_keyword))
    
    if status_filter and status_filter != 'all':
        try:
            status_enum = MatchStatus[status_filter.upper()]
            query = query.filter(Match.status == status_enum)
        except KeyError:
            flash("유효하지 않은 매칭 상태입니다.", 'danger')

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Match.created_at >= start_date)
        except ValueError:
            flash("유효하지 않은 시작 날짜 형식입니다.", 'danger')

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            query = query.filter(Match.created_at <= end_date.replace(hour=23, minute=59, second=59))
        except ValueError:
            flash("유효하지 않은 종료 날짜 형식입니다.", 'danger')

    matches = query.order_by(Match.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # 팝업을 위한 전문가 목록
    experts = User.query.filter_by(user_type=UserType.EXPERT, is_active=True).all()

    return render_template(
        'match/matches.html', 
        matches=matches, 
        experts=experts,
        user_id_keyword=user_id_keyword,
        expert_id_keyword=expert_id_keyword,
        status_filter=status_filter,
        start_date=start_date_str,
        end_date=end_date_str
    )

@match.route('/batch_assign_expert', methods=['POST'])
@login_required
@admin_required
def batch_assign_expert():
    match_ids = request.form.getlist('match_ids')
    expert_id = request.form.get('expert_id')

    if not match_ids or not expert_id:
        flash('매칭 ID와 전문가를 모두 선택해야 합니다.', 'danger')
        return redirect(url_for('match.manage_matches'))

    expert = User.query.get(expert_id)
    if not expert or expert.user_type != UserType.EXPERT:
        flash('유효하지 않은 전문가입니다.', 'danger')
        return redirect(url_for('match.manage_matches'))

    matches_to_update = Match.query.filter(Match.id.in_(match_ids)).all()
    count = 0
    for match in matches_to_update:
        if match.status == MatchStatus.UNASSIGNED:
            match.expert_id = expert.id
            match.status = MatchStatus.IN_PROGRESS
            
            # 매칭 로그 기록
            log = MatchLog(
                admin_id=current_user.id,
                user_id=match.user_id,
                expert_id=expert.id,
                match_id=match.id,
                match_status=MatchStatus.IN_PROGRESS,
                action_summary=f'관리자({current_user.email})가 사용자({match.user.email})를 전문가({expert.email})와 매칭',
                details='일괄 매칭'
            )
            db.session.add(log)
            count += 1
    
    try:
        db.session.commit()
        flash(f'{count}개의 매칭이 성공적으로 업데이트되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'매칭 업데이트 중 오류 발생: {e}', 'danger')

    return redirect(url_for('match.manage_matches'))


@match.route('/batch_end_match', methods=['POST'])
@login_required
@admin_required
def batch_end_match():
    match_ids = request.form.getlist('match_ids')
    action = request.form.get('action')

    if not match_ids or action not in ['complete', 'cancel']:
        flash('매칭 ID와 유효한 작업을 선택해야 합니다.', 'danger')
        return redirect(url_for('match.manage_matches'))

    matches_to_update = Match.query.filter(Match.id.in_(match_ids)).all()
    count = 0
    for match in matches_to_update:
        if match.status == MatchStatus.IN_PROGRESS:
            new_status = MatchStatus.COMPLETED if action == 'complete' else MatchStatus.CANCELLED
            
            # 매칭 상태 업데이트
            match.status = new_status
            match.closed_at = func.now()
            
            # 매칭 로그 기록
            log = MatchLog(
                admin_id=current_user.id,
                user_id=match.user_id,
                expert_id=match.expert_id,
                match_id=match.id,
                match_status=new_status,
                action_summary=f'관리자({current_user.email})가 매칭을 {new_status.value} 처리',
                details='일괄 매칭 해제'
            )
            db.session.add(log)
            count += 1
    
    try:
        db.session.commit()
        flash(f'{count}개의 매칭이 성공적으로 해제(종료)되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'매칭 해제 중 오류 발생: {e}', 'danger')

    return redirect(url_for('match.manage_matches'))
