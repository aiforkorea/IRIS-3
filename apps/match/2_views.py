# apps/match/views.py
import csv
from io import StringIO
from datetime import datetime, time
from flask import render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from sqlalchemy import or_, cast, String
from sqlalchemy.sql import func
from sqlalchemy.orm import aliased  # Import aliased function
from sqlalchemy.orm import joinedload

# apps.extensions에서 db를 가져옵니다.
from apps.extensions import db

from apps.match.forms import LogSearchForm, MatchSearchForm, NewMatchForm, AdminLogSearchForm
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
@admin_required
def match_manager():
    # admin_required를 제거하고 필요에 따라 함수 내부에서 확인
    if not current_user.is_authenticated or not current_user.user_type == UserType.ADMIN:
        flash("접근 권한이 없습니다.", "danger")
        return redirect(url_for('auth.login'))

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

    # 신규 매칭 사용자 검색 폼 (상단)
    if request.method == 'POST' and 'search_submit' in request.form:
        new_match_form.process(request.form)
        if new_match_form.validate_on_submit():
            keyword = request.form.get('keyword')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            params = {'search_type': 'new'} # 수정된 부분: 검색 타입을 지정
            if keyword:
                params['keyword'] = keyword
            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date
            return redirect(url_for('match.match_manager', **params))
    
    # GET 파라미터로 검색 조건 취득
    search_type = request.args.get('search_type', 'new', type=str) # 수정된 부분: 검색 타입 파라미터 추가
    keyword_query = request.args.get('keyword', '', type=str)
#    status_query = request.args.get('status', 'all', type=str)

    # --- 수정된 부분 ---
    # status 파라미터가 없으면 'IN_PROGRESS'를 기본값으로 사용
    status_query = request.args.get('status')
    if status_query is None:
        status_query = 'IN_PROGRESS'
    # --- 수정 끝 ---

    start_date_query = request.args.get('start_date', type=str)
    end_date_query = request.args.get('end_date', type=str)

    start_date_val = None
    if start_date_query:
        try:
            start_date_val = datetime.date.fromisoformat(start_date_query)
        except Exception:
            start_date_val = None

    end_date_val = None
    if end_date_query:
        try:
            end_date_val = datetime.date.fromisoformat(end_date_query)
        except Exception:
            end_date_val = None

    # 신규 매칭 탭의 사용자 목록
    new_match_query = User.query.filter(
        User.user_type == UserType.USER,
        User.match_status == MatchStatus.UNASSIGNED,
        User.is_active == True,
        User.is_deleted == False
    )
    if search_type == 'new' and keyword_query: # 수정된 부분: search_type이 'new'일 때만 필터 적용
        new_match_query = new_match_query.filter(
            or_(
                cast(User.id, String).ilike(f'%{keyword_query}%'),
                User.username.ilike(f'%{keyword_query}%'),
                User.email.ilike(f'%{keyword_query}%')
            )
        )
    if start_date_val and search_type == 'new':
        new_match_query = new_match_query.filter(User.created_at >= start_date_val)
    if end_date_val and search_type == 'new':
        new_match_query = new_match_query.filter(User.created_at <= end_date_val + datetime.timedelta(days=1))
    
    users_to_match = new_match_query.order_by(User.created_at.desc()).all()

    # 기존 매칭 관리 탭 로직
    page = request.args.get('page', 1, type=int)
    expert_alias = aliased(User)
    matches_query = db.session.query(Match).join(User, Match.user_id == User.id).outerjoin(expert_alias, Match.expert_id == expert_alias.id)

    filtered_args = {'search_type': 'manage'} #  수정된 부분: 매칭 관리 검색 타입 지정
    if search_type == 'manage': #  수정된 부분: search_type이 'manage'일 때만 필터 적용
        if keyword_query:
            matches_query = matches_query.filter(
                or_(
                    cast(Match.id, String).ilike(f'%{keyword_query}%'),
                    cast(User.id, String).ilike(f'%{keyword_query}%'),
                    cast(expert_alias.id, String).ilike(f'%{keyword_query}%'),
                    User.username.ilike(f'%{keyword_query}%'),
                    expert_alias.username.ilike(f'%{keyword_query}%'),
                    User.email.ilike(f'%{keyword_query}%'),
                    expert_alias.email.ilike(f'%{keyword_query}%')
                )
            )
            filtered_args['keyword'] = keyword_query

        # --- 수정된 부분 ---
        # status_query가 'all'이 아닐 경우에만 필터링 (기존 로직 유지)
        if status_query != 'all':
            matches_query = matches_query.filter(Match.status == MatchStatus[status_query])
        # 페이지네이션을 위해 현재 status 값을 filtered_args에 추가
        filtered_args['status'] = status_query
        # --- 수정 끝 ---
            
        if start_date_val:
            matches_query = matches_query.filter(Match.created_at >= start_date_val)
            filtered_args['start_date'] = start_date_val.isoformat()
        if end_date_val:
            matches_query = matches_query.filter(Match.created_at <= end_date_val + datetime.timedelta(days=1))
            filtered_args['end_date'] = end_date_val.isoformat()
    
    pagination = matches_query.order_by(Match.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    matches_history = pagination.items

    # 카운트 정보
    unassigned_matches_count = User.query.filter(
        User.user_type == UserType.USER,
        User.match_status == MatchStatus.UNASSIGNED,
        User.is_active == True,
        User.is_deleted == False
    ).count()
    in_progress_matches_count = Match.query.filter(
        Match.status.in_([MatchStatus.IN_PROGRESS])
    ).count()

    # 폼 데이터 바인딩
    new_match_form.process(request.args)
    match_search_form.process(request.args)
    #match_search_form.status.choices = [('all', '모두')] + [(s.name, s.value) for s in MatchStatus]
    match_search_form.status.choices = [('all', '모두')] + [(s.name, s.name) for s in MatchStatus]

    return render_template(
        'match/match_manager.html',
        new_match_form=new_match_form,
        match_search_form=match_search_form,
        users_to_match=users_to_match,
        matches_history=matches_history,
        pagination=pagination,
        unassigned_matches_count=unassigned_matches_count,
        in_progress_matches_count=in_progress_matches_count,
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
                # 전문가 객체를 미리 조회합니다.
                expert_to_match = User.query.get(expert_id)
                expert_username = expert_to_match.username if expert_to_match else "알 수 없는 전문가"

                for user_id in user_ids:
                    user_to_match = User.query.get(user_id)
                    if user_to_match and user_to_match.match_status == MatchStatus.UNASSIGNED:
                        new_match = Match(user_id=user_id, expert_id=expert_id, status=MatchStatus.IN_PROGRESS)  # IN_PROGRESS
                        db.session.add(new_match)
                        
                        db.session.flush()

                        user_to_match.match_status = MatchStatus.IN_PROGRESS
                        print(f'("user_id",user_id)')
                        user_username = user_to_match.username
                        log_summary = f"신규 매칭 생성: 사용자({user_username})({user_id}) - 전문가({expert_username})({expert_id})"
                        
                        match_log = MatchLog(
                            admin_id=current_user.id,
                            user_id=user_id,
                            expert_id=expert_id,
                            match_id=new_match.id,
                            match_status=MatchStatus.IN_PROGRESS,
                            log_title=MatchLogType.MATCH_CREATE.value,
                            log_summary=log_summary
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
 
            # Fetch the new expert's username
            new_expert_user = User.query.get(new_expert_id)
            new_expert_username = new_expert_user.username if new_expert_user else "알 수 없는 전문가"
 
            for match_id in match_ids:
                match_to_update = Match.query.get(match_id)
                if match_to_update and match_to_update.status == MatchStatus.IN_PROGRESS:
                    original_expert_id = match_to_update.expert_id
                    original_expert_user = User.query.get(match_to_update.expert_id)
                    original_expert_username = original_expert_user.username if original_expert_user else "알 수 없는 전문가"
                    
                    match_to_update.expert_id = new_expert_id
                    
                    # --- 수정된 부분 ---
                    log_summary = f"매칭 전문가 변경: 기존({original_expert_username})({original_expert_id}) -> 신규({new_expert_username})({new_expert_id})"
                    
                    match_log = MatchLog(
                        admin_id=current_user.id,
                        user_id=match_to_update.user_id,
                        expert_id=new_expert_id,
                        match_id=match_id,
                        match_status=MatchStatus.IN_PROGRESS,
                        log_title=MatchLogType.MATCH_EXPERT_CHANGE.value,
                        log_summary=log_summary
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
                    match_to_cancel.closed_at = datetime.now()

                    user = User.query.get(match_to_cancel.user_id)
                    expert = User.query.get(match_to_cancel.expert_id)

                    # 사용자 정보 가져오기
                    user_username = user.username if user else "알 수 없는 사용자"
                    user_id = user.id if user else "알 수 없음"

                    # 전문가 정보 가져오기
                    expert_username = expert.username if expert else "알 수 없는 전문가"
                    expert_id = expert.id if expert else "알 수 없음"

                    if user:
                        user.match_status = MatchStatus.UNASSIGNED

                    # --- 수정된 부분: log_summary에 사용자 및 전문가 정보 모두 포함 ---
                    log_summary = f"매치 취소 처리: 사용자({user_username}, ID: {user_id}), 전문가({expert_username}, ID: {expert_id})"

                    match_log = MatchLog(
                        admin_id=current_user.id,
                        match_id=match_id,
                        user_id=match_to_cancel.user_id,
                        expert_id=match_to_cancel.expert_id,
                        match_status=MatchStatus.CANCELLED,
                        log_title=MatchLogType.MATCH_ERASE.value,
                        log_summary=log_summary,
                    )
                    db.session.add(match_log)
                    cancelled_count += 1
            db.session.commit()
            flash(f"총 {cancelled_count}건의 매칭이 취소되었습니다.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"작업 처리 중 오류가 발생했습니다: {str(e)}", "danger")

    # --- 수정된 부분 ---
    # 템플릿의 hidden input으로부터 검색 파라미터를 받음
    redirect_args = {
        'search_type': 'manage',
        'keyword': request.form.get('keyword', ''),
        'status': request.form.get('status', 'IN_PROGRESS'),
        'start_date': request.form.get('start_date', ''),
        'end_date': request.form.get('end_date', '')
    }
    # 빈 값은 전달하지 않도록 정리
    redirect_args = {k: v for k, v in redirect_args.items() if v}

    return redirect(url_for('match.match_manager', **redirect_args))
    # --- 수정 끝 ---

@match.route('/logs', methods=['GET', 'POST'])
@admin_required
def log_list():
    PER_PAGE = 10
    
    # GET/POST 요청 모두 request.form 또는 request.args로 폼 데이터를 바인딩합니다.
    # POST 요청은 request.form, GET 요청은 request.args에 데이터가 있습니다.
    form = AdminLogSearchForm(request.form if request.method == 'POST' else request.args)
    
    filtered_args = {}
    
    # 폼 유효성 검사 및 데이터 추출 (GET/POST 공통 로직)
    # POST 요청일 때는 form.validate_on_submit()으로 유효성 검사
    # GET 요청일 때는 폼에 바인딩된 데이터만 추출
    if form.validate() or request.method == 'GET':
        if form.keyword.data:
            filtered_args['keyword'] = form.keyword.data
        if form.log_title.data:
            filtered_args['log_title'] = form.log_title.data
        if form.start_date.data:
            filtered_args['start_date'] = form.start_date.data.isoformat()
        if form.end_date.data:
            filtered_args['end_date'] = form.end_date.data.isoformat()
    
        # POST 요청일 때만 리디렉션
        if request.method == 'POST':
            # GET 요청으로 필터링 인자를 전달하여 URL을 깨끗하게 유지
            return redirect(url_for('match.log_list', **filtered_args))

    logs_query = MatchLog.query.options(
        joinedload(MatchLog.admin),
        joinedload(MatchLog.user),
        joinedload(MatchLog.expert)
    )

    # 폼 데이터에 따라 쿼리 필터링
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

    page = request.args.get('page', 1, type=int)
    logs_pagination = logs_query.order_by(MatchLog.timestamp.desc()).paginate(
        page=page,
        per_page=PER_PAGE,
        error_out=False
    )
    
    # GET 요청으로 들어올 때 form.data는 None이므로, 쿼리스트링에서 form을 다시 바인딩해야 합니다.
    # 이 부분은 이미 위에서 처리하고 있으므로, render_template에 올바른 form 객체만 넘기면 됩니다.
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
    
    # StringIO의 내용을 가져와서 utf-8-sig로 인코딩합니다.
    output_str = output.getvalue()
    output_bytes = output_str.encode('utf-8-sig')
    output.close()
    # csv 파일을 응답으로 반환
    response = Response(output_bytes, mimetype='text/csv; charset=utf-8-sig')
    response.headers['Content-Disposition'] = f'attachment; filename=matchlog_results_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
    return response