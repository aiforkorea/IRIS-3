# apps/admin/views.py
import csv, logging
from datetime import datetime, time
from io import BytesIO, StringIO
from flask import Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_, cast, String
from sqlalchemy.orm import joinedload
# --- WTForms Imports ---
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from apps.admin.forms import CreateUserForm, EditUserForm
from . import admin
from apps.dbmodels import Log, User, UserLogType, UserType
from apps.decorators import admin_required
from apps.extensions import db
from werkzeug.security import generate_password_hash # 비밀번호 해싱을 위해 사용
from .forms import AdminLogSearchForm

def log_action(title, summary, target_user_id=None, status_code=200):
    """관리자 행동을 로그로 기록하는 헬퍼 함수"""
    try:
        new_log = Log(
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
@admin.route('/dashboard')
@admin_required
def dashboard():
    #total_users = User.query.count()
    total_users = User.query.filter(User.is_deleted == False).count()
    total_services = 3  # AIService.query.count()
    pending_subscriptions = 4 # Subscription.query.filter_by(status='pending').count()
    
    # 최근 7일간 서비스 사용량 (로그인 제외)
    #seven_days_ago = datetime.now() - datetime.timedelta(days=7)
    recent_service_usage = 0

    #recent_service_usage = db.session.query(func.sum(UsageLog.usage_count))\
    #                            .filter(UsageLog.timestamp >= seven_days_ago)\
    #                            .filter(UsageLog.usage_type.notin_([UsageLog.UsageType.LOGIN]))\
    #                            .scalar() or 0

    return render_template('admin/dashboard.html',
                           title='관리자 대시보드',
                           total_users=total_users,
                           total_services=total_services,
                           pending_subscriptions=pending_subscriptions,
                           recent_service_usage=recent_service_usage)
@admin.route('/users', methods=['GET'])
@admin_required
def users():
    PER_PAGE = 10
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '', type=str)
    # logging
    current_app.logger.debug("search_query: %s", search_query)
    # --- New search parameters ---
    user_type_query = request.args.get('user_type', '', type=str) # 'admin', 'expert', or 'user'
    is_active_query = request.args.get('is_active', '', type=str) # 'true', 'false', or ''
    created_at_query = request.args.get('created_at', '', type=str) # YYYY-MM-DD format
    # ---------------------------
    # [수정] users_query = User.query 기본 쿼리에 is_deleted == False 조건을 추가합니다.
    users_query = User.query.filter(User.is_deleted == False)
    # logging
    current_app.logger.debug("users_query: %s", users_query)

    # 검색 기능 (사용자 이름 또는 이메일)
    if search_query:
        users_query = users_query.filter(
            or_(
                User.username.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%')
            )
        )
    # 사용자 타입(관리자, 전문가, 사용자) 여부 필터링
#    if user_type_query :
#        if user_type_query == 'admin': 
#            users_query = users_query.filter(User.user_type == UserType.ADMIN)
#        elif user_type_query == 'expert':
#            users_query = users_query.filter(User.user_type == UserType.EXPERT)
#        elif user_type_query == 'user':
#            users_query = users_query.filter(User.user_type == UserType.USER)
# 동일 코드
    if user_type_query and user_type_query in [e.value for e in UserType]:
        users_query = users_query.filter(User.user_type == UserType(user_type_query))

    # 활성 상태 필터링
#    if is_active_query:
#        if is_active_query == 'true':
#            users_query = users_query.filter(User.is_active == True)
#        elif is_active_query == 'false':
#            users_query = users_query.filter(User.is_active == False)
# 동일 코드
    if is_active_query:
        is_active_bool = is_active_query.lower()=='true'
        users_query = users_query.filter(User.is_active == is_active_bool)
    # 가입일 필터링
    if created_at_query:
        try:
            # Parse the date string. We want to filter for users created ON that specific date.
            # So, from the start of that day up to the end of that day.
            search_date = datetime.strptime(created_at_query, '%Y-%m-%d').date()
            start_of_day = datetime.combine(search_date, time.min)
            end_of_day = datetime.combine(search_date, time.max)
            users_query = users_query.filter(User.created_at >= start_of_day, User.created_at <= end_of_day)
            #users_query = users_query.filter(User.created_at.between(start_of_day, end_of_day))
        except ValueError:
            flash('유효하지 않은 가입일 형식입니다. YYYY-MM-DD 형식으로 입력해주세요.', 'warning')
            created_at_query = ""
    # 페이지네이션 적용
    users_pagination = users_query.order_by(User.created_at.desc()).paginate(page=page, per_page=PER_PAGE, error_out=False)
    users = users_pagination.items
    # request.args에서 'page'만 뺀 딕셔너리 준비해서 템플릿에 넘긴다
    filtered_args = request.args.to_dict(flat=True)
    filtered_args.pop('page', None)
    return render_template(
        'admin/users.html',
        title='사용자 관리',
        users=users_pagination.items,
        pagination=users_pagination,
        search_query=search_query,
        user_type_query=user_type_query,
        is_active_query=is_active_query,
        created_at_query=created_at_query,
        UserType=UserType,           # 템플릿에서 Enum을 사용하기 위해 전달
        filtered_args=filtered_args, # <-- 추가
    )
@admin.route('/users/<string:user_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    # [수정]     user = User.query.get_or_404(user_id)의 get_or_404를 filter_by와 first_or_404로 변경하여 삭제된 사용자는 조회되지 않게 함
    user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()

    if user.id == current_user.id:
        flash('자신의 계정 상태는 변경할 수 없습니다.', 'warning')
        return redirect(url_for('admin.users'))
    try:
        user.is_active = not user.is_active
        action = "활성" if user.is_active else "비활성"
        #summary = f"'{user.username}'(ID:{user.id}) 계정을 {action} 상태로 변경."
        summary = f"'{user.username}' 계정을 {action} 상태로 변경."
        log_action(title="계정상태변경", summary=summary, target_user_id=user.id)

        db.session.commit()
        flash(f'{user.username} 계정 상태가 {action}으로 변경되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'계정 상태 변경 중 오류 발생: {e}', 'danger')
    return redirect(url_for('admin.users', **request.args)) # 기존 검색/필터 조건(request.args) 유지
@admin.route('/user_type_change/<string:user_id>', methods=['POST'])
@admin_required
def user_type_change(user_id):
    # user = User.query.get_or_404(user_id)의 get_or_404를 filter_by와 first_or_404로 변경
    # 1. 레코드 조회 
    user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
    print(f"user: {user}")   # log 사용
    if user.id == current_user.id:
        flash('자신의 관리자 권한은 변경할 수 없습니다.', 'warning')
        return redirect(url_for('admin.users'))
    new_user_type_str = request.form.get('user_type')
    if new_user_type_str in [e.value for e in UserType]:
        try:
            original_type = user.user_type.value
            user.user_type = UserType(new_user_type_str)
            #summary = f"'{user.username}'(ID:{user.id}) 역할을 '{original_type}'에서 '{new_user_type_str}'(으)로 변경."
            summary = f"'{user.username}' 역할을 '{original_type}'에서 '{new_user_type_str}'(으)로 변경."
            log_action(title="사용자역할변경", summary=summary, target_user_id=user.id)
            db.session.commit()
            flash(f'사용자 역할 변경이 성공적으로 처리되었습니다.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'처리 중 오류가 발생했습니다: {e}', 'danger')
    else:
        flash('유효하지 않은 사용자 역할입니다.', 'danger')
    return redirect(url_for('admin.users', **request.args))
@admin.route('/users/<string:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    # [수정] user = User.query.get_or_404(user_id)의 get_or_404를 filter_by와 first_or_404로 변경
    user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
    form = EditUserForm(original_user=user)
    if form.validate_on_submit():
        try:
            original_username = user.username
            original_email = user.email
            user.username = form.username.data
            user.email = form.email.data
            #summary = f"'{original_username}'(ID:{user.id}) 정보 변경. "
            summary = f"'{original_username}' 정보 변경. "
            if original_username != user.username:
                summary += f"이름: '{original_username}'->'{user.username}'. "
            if original_email != user.email:
                summary += f"이메일: '{original_email}'->'{user.email}'."
            log_action(title="사용자정보수정", summary=summary, target_user_id=user.id)
            db.session.commit()
            flash(f'{user.username}님의 정보가 성공적으로 수정되었습니다.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            db.session.rollback()
            flash(f'사용자 정보 수정 중 오류가 발생했습니다: {e}', 'danger')
    # GET 요청 시, 폼에 현재 사용자 정보를 채워서 전달
    form.username.data = user.username
    form.email.data = user.email
    return render_template('admin/edit_user.html', title=f'{user.username} 수정', form=form, user=user)
@admin.route('/users/<string:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    # [수정] user = User.query.get_or_404(user_id)의 get_or_404를 filter_by와 first_or_404로 변경
    user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
    if user.id == current_user.id:
        flash('자신의 계정은 삭제할 수 없습니다.', 'warning')
        return redirect(url_for('admin.users', **request.args))
    # 이미 삭제된 사용자인지 확인
    if user.is_deleted:
        flash(f'이미 삭제된 사용자입니다.', 'info')
        return redirect(url_for('admin.users', **request.args))
    try:
        # User 모델에 정의된 soft_delete 메서드 호출 (아래 추가 제안 참조)
        # 이 메서드가 없다면 AttributeError가 발생합니다.
        user.soft_delete() 
        summary = f"'{user.username}' 계정을 삭제 처리."
        log_action(title="사용자삭제", summary=summary, target_user_id=user.id)
        db.session.commit()
        flash(f'{user.username} 계정이 성공적으로 삭제 처리되었습니다.', 'success')
    except AttributeError:
        db.session.rollback()
        flash(f'soft_delete 메서드가 User 모델에 정의되지 않았습니다.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'사용자 삭제 중 오류가 발생했습니다: {e}', 'danger')
    return redirect(url_for('admin.users', **request.args))

@admin.route('/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    form = CreateUserForm()
    if form.validate_on_submit():
        print("create starts")
        try:
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                password=form.password.data,
                user_type=UserType(form.user_type.data),
                is_active=form.is_active.data
            )
            db.session.add(new_user)
            db.session.flush()
            #summary = f"신규 사용자 '{new_user.username}'(ID:{new_user.id}, 역할:{new_user.user_type.value}) 생성."
            summary = f"신규 사용자 '{new_user.username}', 역할:{new_user.user_type.value} 생성."
            log_action(title="사용자생성", summary=summary, target_user_id=new_user.id)
            db.session.commit()
            flash(f'{new_user.username} 사용자가 성공적으로 생성되었습니다.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            db.session.rollback()
            flash(f'사용자 생성 중 오류가 발생했습니다: {e}', 'danger')
    return render_template('admin/create_user.html', title='사용자 생성', form=form)

@admin.route('/logs', methods=['GET', 'POST'])
@admin_required
def log_list():
    PER_PAGE = 10
    
    form = AdminLogSearchForm()
    
    logs_query = Log.query.options(joinedload(Log.actor))
    filtered_args = {}

    if form.validate_on_submit():
        # POST 요청: 폼 데이터를 처리하고 GET 요청으로 리디렉션 (PRG 패턴)
        filtered_args['keyword'] = form.keyword.data if form.keyword.data else ''
        filtered_args['log_title'] = form.log_title.data if form.log_title.data else ''
        filtered_args['start_date'] = form.start_date.data.isoformat() if form.start_date.data else ''
        filtered_args['end_date'] = form.end_date.data.isoformat() if form.end_date.data else ''
        return redirect(url_for('admin.log_list', **filtered_args))
    
    elif request.method == 'GET':
        # GET 요청: URL의 쿼리 파라미터로 폼을 채움
        form = AdminLogSearchForm(request.args)
        
    # GET 또는 POST 리디렉션 후 필터링 로직
    # 폼 데이터가 유효한 경우에만 필터링을 적용
    if form.keyword.data:
        keyword = f"%{form.keyword.data}%"
        logs_query = logs_query.join(User, Log.user_id == User.id, isouter=True).filter(
            or_(
                cast(Log.id, String).ilike(keyword),
                cast(Log.target_user_id, String).ilike(keyword),
                Log.endpoint.ilike(keyword),
                Log.log_title.ilike(keyword),
                Log.log_summary.ilike(keyword),
                User.username.ilike(keyword)
            )
        )
        filtered_args['keyword'] = form.keyword.data

    if form.log_title.data:
        logs_query = logs_query.filter(Log.log_title == form.log_title.data)
        filtered_args['log_title'] = form.log_title.data
    
    if form.start_date.data:
        start_of_day = datetime.combine(form.start_date.data, time.min)
        logs_query = logs_query.filter(Log.timestamp >= start_of_day)
        filtered_args['start_date'] = form.start_date.data.isoformat()
        
    if form.end_date.data:
        end_of_day = datetime.combine(form.end_date.data, time.max)
        logs_query = logs_query.filter(Log.timestamp <= end_of_day)
        filtered_args['end_date'] = form.end_date.data.isoformat()

    page = request.args.get('page', 1, type=int)
    logs_pagination = logs_query.order_by(Log.timestamp.desc()).paginate(
        page=page, 
        per_page=PER_PAGE, 
        error_out=False
    )
    
    return render_template(
        'admin/logs.html',
        title='로그 조회',
        form=form,
        logs=logs_pagination.items,
        pagination=logs_pagination,
        filtered_args=filtered_args,
    )

"""
@admin.route('/logs', methods=['GET'])
@admin_required
def log_list():
    PER_PAGE = 10
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search_query', '', type=str)
    log_title_query = request.args.get('log_title_query', '', type=str)
    start_date = request.args.get('start_date', '', type=str)
    end_date = request.args.get('end_date', '', type=str)

    # [FIXED] N+1 문제를 방지하기 위해 joinedload로 'actor' 정보를 함께 가져옵니다.
    logs_query = Log.query.options(joinedload(Log.actor))

    # 검색 기능
    # [수정] 검색 기능 로직을 if 블록 안으로 완전히 이동
    # 1. 일반 검색어 필터링
    if search_query:
        search_filter = or_(
            cast(Log.user_id, String).ilike(f'%{search_query}%'),
            cast(Log.target_user_id, String).ilike(f'%{search_query}%'),
            Log.endpoint.ilike(f'%{search_query}%'),
            Log.log_title.ilike(f'%{search_query}%'),
            Log.log_summary.ilike(f'%{search_query}%'),
            # actor의 username으로 검색하기 위해 Log.actor 관계를 통해 join
            User.username.ilike(f'%{search_query}%')
        )
        # join과 filter를 if 블록 안에서만 실행
        logs_query = logs_query.join(Log.actor).filter(search_filter)

    # 2. [추가] 로그 제목 필터링
    if log_title_query:
        logs_query = logs_query.filter(Log.log_title == log_title_query)
    # 3. 날짜 필터링
    try:
        if start_date:
            search_start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            start_of_day = datetime.combine(search_start_date, time.min)
            logs_query = logs_query.filter(Log.timestamp >= start_of_day)
        
        if end_date:
            search_end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            end_of_day = datetime.combine(search_end_date, time.max)
            logs_query = logs_query.filter(Log.timestamp <= end_of_day)
    except ValueError:
        flash('유효하지 않은 날짜 형식입니다. YYYY-MM-DD 형식으로 입력해주세요.', 'warning')
        start_date = ""
        end_date = ""

    logs_pagination = logs_query.order_by(Log.timestamp.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )

    filtered_args = request.args.to_dict(flat=True)
    filtered_args.pop('page', None)

    return render_template(
        'admin/logs.html',
        title='로그 조회',
        logs=logs_pagination.items,
        pagination=logs_pagination,
        filtered_args=filtered_args,
        UserLogType=UserLogType, # 템플릿에 UserLogType Enum을 전달해야 합니다.
        log_title_query=log_title_query, # 템플릿에 log_title_query를 전달
        search_params={
            'search_query': search_query, # search_query도 전달하는 것이 좋습니다.
            'log_title_query': log_title_query,
            'start_date': start_date,
            'end_date': end_date
        }
    )
"""
@admin.route('/logs/download-csv', methods=['GET'])
@admin_required
def logs_download_csv():
    # logging
    current_app.logger.debug("Starting: %s", "download")
    # 1. 검색 쿼리 패러미터
    search_query = request.args.get('search_query', '', type=str)
    log_title_query = request.args.get('log_title_query', '', type=str)
    start_date = request.args.get('start_date', '', type=str)
    end_date = request.args.get('end_date', '', type=str)
    # 2. [수정] N+1 문제 방지 및 안정성 확보를 위해 joinedload와 join을 분리
    logs_query = Log.query.options(joinedload(Log.actor))
    # 3. 검색 기능
    # 3.1 일반 검색어 필터링
    if search_query:
        search_filter = or_(
            cast(Log.user_id, String).ilike(f'%{search_query}%'),
            cast(Log.target_user_id, String).ilike(f'%{search_query}%'),
            Log.endpoint.ilike(f'%{search_query}%'),
            Log.log_title.ilike(f'%{search_query}%'),
            Log.log_summary.ilike(f'%{search_query}%'),
            User.username.ilike(f'%{search_query}%')
        )
        # join은 search_query에 사용자 이름이 포함된 경우에만 추가합니다.
        logs_query = logs_query.join(Log.actor).filter(search_filter)
    # 3.2 로그 제목 필터링
    if log_title_query:
        logs_query = logs_query.filter(Log.log_title == log_title_query)
    # 3.3 날짜 필터링
    try:
        if start_date:
            search_start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            start_of_day = datetime.combine(search_start_date, time.min)
            logs_query = logs_query.filter(Log.timestamp >= start_of_day)
        if end_date:
            search_end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            end_of_day = datetime.combine(search_end_date, time.max)
            logs_query = logs_query.filter(Log.timestamp <= end_of_day)
    except ValueError:
        flash('유효하지 않은 날짜 형식입니다. YYYY-MM-DD 형식으로 입력해주세요.', 'warning')
        # 오류 발생 시 필터링을 중단하고 페이지를 리디렉션합니다.
        return redirect(url_for('admin.log_list', **request.args))
    current_url = request.url
    # logging
    current_app.logger.debug("CSV 다운로드 요청 URL: %s", current_url)
    # 현재 URL에서 쿼리 파라미터(필터링 조건) 추출
    search_params = request.args.to_dict()
    current_app.logger.debug("CSV 다운로드 필터링 조건: %s", search_params)
    # 4. 쿼리 실행(검색한 모든 결과 가져오기)
    logs_results = logs_query.order_by(Log.timestamp.desc()).all()
    # 5. CSV 데이터 생성
    si = StringIO()
    cw = csv.writer(si)
    # 6. CSV 헤더(컬럼이름)
    headers = ['ID', '사용자(ID)', '대상(ID)', '엔드포인트', '로그제목', '내용요약', '타임스탬프']
    cw.writerow(headers)
    # 7. 데이터 행 추가
    for logs_result in logs_results:
        timestamp_str = f"'{logs_result.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')}"
        row = [
            logs_result.id,
            logs_result.user_id,
            logs_result.target_user_id,
            logs_result.endpoint,
            logs_result.log_title,
            logs_result.log_summary,
            timestamp_str
        ]
        cw.writerow(row)
    # StringIO의 내용을 가져와서 utf-8-sig로 인코딩합니다.
    output_str = si.getvalue()
    output_bytes = output_str.encode('utf-8-sig')
    si.close()
    # csv 파일을 응답으로 반환
    response = Response(output_bytes, mimetype='text/csv; charset=utf-8-sig')
    response.headers['Content-Disposition'] = f'attachment; filename=userlog_results_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
    return response