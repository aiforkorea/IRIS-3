# apps/iris/views.py
from flask import Flask, flash, redirect, request, render_template, jsonify, abort, current_app, url_for, g
import pickle, os
import logging, functools
from sqlalchemy import desc, func
from apps.extensions import csrf
# apps.dbmodels 에서 User, APIKey, UsageLog, UsageType 등을 가져오고
from apps.dbmodels import PredictionResult, db, APIKey, UsageLog, UsageType, Service
# apps.iris.dbmodels 에서 IrisResult 모델을 가져옵니다.
from apps.iris.dbmodels import IrisResult
import numpy as np
from flask_login import current_user, login_required
from apps.iris.forms import EmptyForm, IrisUserForm
from . import iris
from datetime import datetime, timedelta

# Load model
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model.pkl')
with open(MODEL_PATH, 'rb') as f:
    model = pickle.load(f)

TARGET_NAMES = ['setosa', 'versicolor', 'virginica']
from apps.config import Config
#TARGET_NAMES = Config.IRIS_LABELS   # 라벨 읽기

#0: Iris-Setosa
#1: Iris-Versicolor
#2: Iris-Virginica

# AI 사용량 제한 데코레이터
def rate_limit(limit_config_key):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            limit_str = getattr(Config, limit_config_key)
            # 간단한 속도 제한 구현 (프로덕션에서는 Redis 등을 활용하는 것이 좋습니다)
            # 현재는 UsageLog 테이블을 사용하여 카운트합니다.
            # 이 로직은 실제 배포 시 성능 문제가 될 수 있으므로 주의가 필요합니다.
            # Flask-Limiter와 같은 외부 라이브러리를 사용하는 것을 권장합니다.
            # API Key 사용량 제한
            if 'api_key_id' in kwargs and kwargs['api_key_id']:
                api_key = APIKey.query.get(kwargs['api_key_id'])
                if not api_key:
                    logging.warning(f"Rate Limit: Invalid API Key ID {kwargs['api_key_id']}")
                    return jsonify({"error": "Invalid API Key"}), 401
                # 현재 분의 시작 시간 계산
                now = datetime.now()
                minute_ago = now - timedelta(minutes=1)
                usage_count = UsageLog.query.filter(
                    UsageLog.api_key_id == api_key.id,
                    UsageLog.endpoint == request.path,
                    UsageLog.timestamp >= minute_ago
                ).count()
                limit_value = int(limit_str.split('/')[0])
                if usage_count >= limit_value:
                    logging.warning(f"Rate Limit Exceeded for API Key {api_key.key_string}. Count: {usage_count}, Limit: {limit_value}")
                    return jsonify({"error": "API Key usage limit exceeded. Please try again later."}), 429
                # API Key 사용량 업데이트
                api_key.usage_count += 1
                api_key.last_used = now
                db.session.commit() # 여기서 커밋하여 바로 반영
            # 로그인 사용자 사용량 제한
            elif current_user.is_authenticated:
                # 현재 시간의 시작 시간 (시간당)
                now = datetime.now()
                hour_ago = now - timedelta(hours=1)
                usage_count = UsageLog.query.filter(
                    UsageLog.user_id == current_user.id,
                    UsageLog.endpoint == request.path,
                    UsageLog.timestamp >= hour_ago
                ).count()
                limit_value = int(limit_str.split('/')[0])
                if usage_count >= limit_value:
                    logging.warning(f"Rate Limit Exceeded for User {current_user.email}. Count: {usage_count}, Limit: {limit_value}")
                    flash('시간당 사용량 제한을 초과했습니다. 잠시 후 다시 시도해주세요.', 'warning')
                    return redirect(url_for('iris.predict')) # 또는 에러 페이지로 리디렉션
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@iris.route('/services')
def services():
    # logging
    current_app.logger.debug("search_query: %s", "Starts services")
    return render_template('iris/services.html')

@iris.route('/iris_predict', methods=['GET', 'POST'])
@login_required
def iris_predict():
    print("predict 시작")
    form = IrisUserForm()
    if form.validate_on_submit():
        sepal_length = form.sepal_length.data
        sepal_width = form.sepal_width.data
        petal_length = form.petal_length.data
        petal_width = form.petal_width.data
      
        features = np.array([[sepal_length, sepal_width, petal_length, petal_width]])

        # 0.1 중복 레코드 확인
        existing_result = IrisResult.query.filter_by(
            sepal_length=sepal_length,
            sepal_width=sepal_width,
            petal_length=petal_length,
            petal_width=petal_width,
            user_id=current_user.id # 현재 사용자가 동일한 값을 입력했는지 확인
        ).first()

        # 0.2 중복 레코드가 있는 경우
        if existing_result:
            flash("이미 존재하는 값입니다. 기존 예측 결과를 표시합니다.", 'info')
           
            # 기존 결과를 사용하여 템플릿 렌더링
            return render_template('iris/predict.html',
                                    result=existing_result.predicted_class,
                                    sepal_length=sepal_length,
                                    sepal_width=sepal_width,
                                    petal_length=petal_length,
                                    petal_width=petal_width,
                                    form=form,
                                    TARGET_NAMES=TARGET_NAMES,
                                    iris_result_id=existing_result.id,
                                    allow_confirm_save=False) # 확인 저장 비활성화
        # 0.3 중복 레코드가 없는 경우
        else:
            pred = model.predict(features)[0]
            print(f"예측 값 0부터 시작하는 지 확인: {pred}")  # pred는 0부터 시작
            # 1. 'iris' 서비스의 ID를 조회합니다.
            # 만약 서비스가 없으면 None으로 처리하거나 오류를 낼 수 있습니다.
            #iris_service = Service.query.filter_by(servicename='iris').first()   # Service 테이블의 servicename이 'iris'인 서비스 조회
            # 만약 서비스가 없으면 None이 될 수 있으므로, 이 부분을 수정
            #iris_service_id = iris_service.id if iris_service else None
            iris_service_id = 1   # 서비스 번호는 임의로 설정, 향후 다중 서비스인 경우, 해당 ID 할당 예정

            # 2. IrisResult 객체 생성 시 service_id에 찾은 값을 할당합니다.
            new_iris_result = IrisResult(
                user_id=current_user.id,
                service_id=iris_service_id,  # 이 부분을 수정
                sepal_length=sepal_length,
                sepal_width=sepal_width,
                petal_length=petal_length,
                petal_width=petal_width,
                #predicted_class=TARGET_NAMES[pred-1],  # pred는 1부터 시작하므로 -1
                predicted_class=TARGET_NAMES[pred],  # pred는 0부터 시작
                model_version='1.0',  # 모델 버전 정보 추가
                confirm=False  # 초기 상태는 False로 설정
            )
            db.session.add(new_iris_result)
            db.session.flush() # ID를 얻기 위해 일단 flush (커밋은 나중에)

            # 3. UsageLog 객체 생성 시 service_id에 찾은 값을 할당합니다.
            new_usage_log = UsageLog(
                user_id=current_user.id,
                usage_type=UsageType.WEB_UI, # WEB_UI 사용으로 변경
                endpoint=request.path,
                remote_addr=request.remote_addr,
                response_status_code=200,
                inference_timestamp=datetime.now(), # 추론시각을 별도로 기록
                service_id=iris_service_id, # 이 부분을 수정
                prediction_result_id=new_iris_result.id # 여기를 추가!
            )
            db.session.add(new_usage_log)
            db.session.commit()

            # db.session.commit() 이후에 IrisResult의 ID를 확인하고 템플릿에 전달
            iris_result_id = new_iris_result.id
            print(f"새로 생성된 IrisResult의 ID: {iris_result_id}")
            return render_template('iris/predict.html',
                                result=TARGET_NAMES[pred],
                                sepal_length=sepal_length, sepal_width=sepal_width,
                                petal_length=petal_length, petal_width=petal_width, form=form,
                                TARGET_NAMES=TARGET_NAMES, iris_result_id=iris_result_id,
                                allow_confirm_save=True) # 확인 저장 활성화
    return render_template('iris/predict.html', form=form)

@iris.route('/save_iris_data', methods=['POST'])
@login_required
def save_iris_data():
    if request.method == 'POST':
# 폼 데이터 가져오기
        iris_result_id = request.form.get('iris_result_id')
        confirmed_class = request.form.get('confirmed_class')

        # created_id가 없으면 오류 처리
        if not iris_result_id:
            flash('유효한 데이터 ID가 없습니다.', 'danger')
            return redirect(url_for('iris.iris_predict'))

        try:
            # created_id를 사용하여 IrisResult 레코드 조회
            # first_or_404()를 사용하면 레코드가 없을 경우 404 에러를 반환
            iris_result = IrisResult.query.filter_by(id=iris_result_id).first_or_404()
            
            # 레코드 업데이트
            iris_result.confirmed_class = confirmed_class
            iris_result.confirm = True
            iris_result.confirmed_at = datetime.now()

            # 변경사항 커밋
            db.session.commit()
            # 데이터 업데이트가 성공했음을 확인하는 print 문 추가
            print(f"IrisResult with ID {iris_result_id} has been successfully updated.")
            print(f"Updated values: confirmed_class='{iris_result.confirmed_class}', confirm={iris_result.confirm}")

            # 성공 메시지  
            flash('데이터가 성공적으로 저장되었습니다.', 'success')
            return redirect(url_for('iris.iris_predict'))

        except Exception as e:
            db.session.rollback() # 오류 발생 시 롤백
            flash(f'데이터 저장 중 오류가 발생했습니다: {e}', 'danger')
            return redirect(url_for('iris.iris_predict'))
            
    # POST 요청이 아닌 경우
    flash('잘못된 접근입니다.', 'danger')
    return redirect(url_for('iris.iris_predict'))

"""
@iris.route('/results')
@login_required
def results():
    # `PredictionResult`의 하위 클래스인 `IrisResult`를 쿼리합니다.
    user_results = IrisResult.query.filter_by(user_id=current_user.id).order_by(IrisResult.created_at.desc()).all()
    form = EmptyForm() # 빈 폼 객체를 생성
    return render_template('iris/user_results.html', title='추론결과', results=user_results, form=form) # 템플릿에 form 객체를 전달
"""
@iris.route('/results')
@login_required
def results():
    print("results 시작")
    # 검색 쿼리 파라미터 가져오기
    search_query = request.args.get('search', '', type=str)
    confirm_query = request.args.get('confirm', '', type=str)
    date_filter_type = request.args.get('date_filter_type', '', type=str)
    start_date_str = request.args.get('start_date', '', type=str)
    end_date_str = request.args.get('end_date', '', type=str)
    page = request.args.get('page', 1, type=int)

    # 템플릿으로 전달할 editing_id를 쿼리 파라미터에서 가져옵니다.
    editing_id = request.args.get('editing_id', type=int)

    # 기본 쿼리 (현재 사용자의 결과만)
    query = IrisResult.query.filter_by(user_id=current_user.id)
    
    # 날짜 필터
    has_date_filter_error = False
    if start_date_str or end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

            if start_date and end_date and start_date > end_date:
                flash('시작일은 종료일보다 이전이어야 합니다.', 'danger')
                has_date_filter_error = True
            else:
                filter_col = IrisResult.confirmed_at if date_filter_type == 'confirmed_at' else IrisResult.created_at
                if start_date and end_date:
                    next_day = end_date + timedelta(days=1)
                    query = query.filter(filter_col >= start_date, filter_col < next_day)
                elif start_date:
                    query = query.filter(filter_col >= start_date)
                elif end_date:
                    next_day = end_date + timedelta(days=1)
                    query = query.filter(filter_col < next_day)
        except ValueError:
            flash('날짜 입력이 잘못되었습니다.', 'danger')
            has_date_filter_error = True

    # 날짜 필터 오류가 발생했을 경우, 빈 목록과 페이지네이션 객체를 전달하여 검색을 중단합니다.
    if has_date_filter_error:
        pagination = query.paginate(page=page, per_page=10, error_out=False)
        return render_template(
            'iris/user_results.html',
            title='추론결과',
            results=[],
            form=EmptyForm(),
            pagination=pagination,
            search_query=search_query,
            confirm_query=confirm_query,
            date_filter_type=date_filter_type,
            start_date=start_date_str,
            end_date=end_date_str,
            editing_id=editing_id # editing_id를 템플릿에 전달
        )

    # 검색어(예측, 확인 품종)
    if search_query:
        query = query.filter(
            (IrisResult.predicted_class.ilike(f'%{search_query}%')) |
            (IrisResult.confirmed_class.ilike(f'%{search_query}%'))
        )

    # 동작상태(확인여부)
    if confirm_query:
        if confirm_query == 'true':
            query = query.filter(IrisResult.confirm == True)
        elif confirm_query == 'false':
            query = query.filter(IrisResult.confirm == False)

    # 결과 정렬 (최신 순)
    query = query.order_by(IrisResult.created_at.desc())

    # 페이지네이션 적용
    per_page = 10 # 한 페이지에 보여줄 항목 수
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    user_results = pagination.items # 현재 페이지의 항목들
    form = EmptyForm() # 폼 객체는 삭제 버튼의 CSRF 토큰을 위해 필요

    return render_template(
        'iris/user_results.html',
        title='추론결과',
        results=user_results,
        form=form,
        pagination=pagination, # pagination 객체 전달
        search_query=search_query, # 검색 쿼리 전달
        confirm_query=confirm_query, # 확인 상태 쿼리 전달
        date_filter_type=date_filter_type, # 추가된 부분
        start_date=start_date_str, # 추가된 부분
        end_date=end_date_str # 추가된 부분
    )

# 화면에서 확인된 결과를 업데이트하는 기능을 추가합니다.
# 사용자가 결과를 확인하고 품종을 선택할 수 있도록 합니다.
@iris.route('/confirm_result/<int:result_id>', methods=['POST'])
@login_required
def confirm_result(result_id):
    # 1. 레코드 조회 
    result = IrisResult.query.get_or_404(result_id)
    print(f"result: {result}")
    # 2. 신원/권한 확인 + 레코드 존재 확인
    if result.user_id != current_user.id:
        # 다른 사용자의 결과를 수정하려는 시도 방지
        abort(403)
    # 3. 신규 변경 항목값 확보
    confirmed_class = request.form.get('confirmed_class')

    if confirmed_class in ['setosa', 'versicolor', 'virginica']:
        # 4. 추론 업데이트 처리(필드값 수정)
        result.confirmed_class = confirmed_class
        result.confirm = True
        result.confirmed_at = datetime.now()
        db.session.flush()                        # 변경사항을 데이터베이스에 반영

        # 5. 로그 처리
        try:
            # 1. 추론 ID 중에서 가장 최근 UsageLog 레코드 조회
            # 해당 IrisResult와 연결된 가장 최근 UsageLog를 찾기
            # query에 조건 (filter_by)과 정렬(order_by)을 추가해 가장 최근 레코드를 찾음
            recent_log = (
                UsageLog.query
                .filter_by(prediction_result_id=result.id)  # prediction_result_id(추론ID)가 result.id 인 레코드 필터
                .order_by(desc(UsageLog.timestamp))         # timestamp 내림차순으로 정렬
                .first()                                    # 첫 번째 레코드 (가장 최근 레코드)만 가져옴
            )
            print(f"recent_log: {recent_log}")
       
            # recent_log 확인
            if recent_log:
                print(f"Recent log found: {recent_log.timestamp}")
            else:
                print("No logs found for this prediction_result_id.")
 
            # 2. 신규 UsageLog 객체 생성

            new_usage_log = UsageLog(
                user_id=recent_log.user_id,       # recent_log와 동일
                service_id=recent_log.service_id, # recent_log와 동일
                api_key_id=recent_log.api_key_id, # recent_log와 동일
                endpoint=request.path,            # iris.confirm_result, iris/confirm_result/(result_id를 문자로 표시)
                usage_type=UsageType.WEB_UI,
                log_status='추론확인',             # 추론 -> 추론확인 -> (추론확인한 것을)수정 -> 추론삭제
                inference_timestamp=recent_log.inference_timestamp, # 추론 확인 시각을 recent_log의 추론시각으로 기록(추후 삭제 고려)
                #last_used 마지막 사용 시간이므로, recent_log.inference_timestamp
                remote_addr=request.remote_addr,  # IP 주소
                #request_data_summary  # 필요없음
                response_status_code = 200,
                prediction_result_id=recent_log.prediction_result_id # recent_log와 동일
            )
            db.session.add(new_usage_log)
            # 4. 두 객체를 하나의 트랜잭션으로 한 번에 커밋합니다.
            db.session.commit()

            flash('추론 확인 및 관련 로그가 성공적으로 처리되었습니다.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'결과 입력 중 오류가 발생했습니다: {e}', 'danger')

    else:
        flash('유효하지 않은 품종입니다.', 'danger')

    return redirect(url_for('iris.results'))

# 수정 버튼 클릭 시 호출될 라우트
@iris.route('/edit_confirmed_class/<int:result_id>', methods=['POST'])
@login_required
def edit_confirmed_class(result_id):
    form = EmptyForm() # EmptyForm 객체를 생성합니다.
    if form.validate_on_submit(): # CSRF 토큰을 포함한 폼 제출이 유효한지 확인합니다.
        result = IrisResult.query.get_or_404(result_id)
        if result.user_id != current_user.id:
            abort(403)

        confirmed_class = request.form.get('confirmed_class')
        if confirmed_class in ['setosa', 'versicolor', 'virginica']:
            try:
                result.confirmed_class = confirmed_class
                result.confirmed_at = datetime.now()
                db.session.commit()

                # 로그 기록 추가 (선택 사항)
                # 기존 로그를 수정하거나, 새로운 로그를 추가할 수 있습니다.
                # 여기서는 새로운 로그를 추가하는 로직을 예시로 둡니다.
                recent_log = UsageLog.query.filter_by(prediction_result_id=result.id).order_by(desc(UsageLog.timestamp)).first()
                if recent_log:
                    new_usage_log = UsageLog(
                        user_id=recent_log.user_id,
                        service_id=recent_log.service_id,
                        api_key_id=recent_log.api_key_id,
                        endpoint=request.path,
                        usage_type=UsageType.WEB_UI,
                        log_status='추론수정',  # 수정된 상태로 로그 기록
                        inference_timestamp=recent_log.inference_timestamp,
                        remote_addr=request.remote_addr,
                        response_status_code=200,
                        prediction_result_id=result.id
                    )
                    db.session.add(new_usage_log)
                    db.session.commit()
            
                flash('확인 품종이 성공적으로 수정되었습니다.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'수정 중 오류가 발생했습니다: {e}', 'danger')
        else:
            flash('유효하지 않은 품종입니다.', 'danger')
    return redirect(url_for('iris.results'))

@iris.route('/delete_result/<int:result_id>', methods=['POST'])
@login_required
def delete_result(result_id):
    """
    주어진 ID에 해당하는 IrisResult를 삭제하고,
    관련 UsageLog의 log_status를 "삭제"로 삭제하고
    inference_stamp에 기존 stamp 값을 복사합니다.
    """
    result = IrisResult.query.get_or_404(result_id)

    # 현재 로그인된 사용자의 결과인지 확인하여 다른 사용자의 데이터 삭제 방지
    if result.user_id != current_user.id:
        flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
        abort(403) # 권한 없음 에러 반환

    try:
        # 1. 관련 UsageLog 레코드 조회 및 업데이트
        # 해당 IrisResult와 연결된 모든 UsageLog를 찾아서 상태를 '삭제'로 변경
        related_logs = UsageLog.query.filter_by(prediction_result_id=result.id).all()
        for log in related_logs:
            log.log_status = "삭제"
            log.inference_stamp = log.timestamp # 기존 timestamp값을 inference_stamp에 저장
            log.timestamp = datetime.now() # 삭제 시점의 시간으로 업데이트
        # 2. IrisResult 레코드 삭제
        db.session.delete(result)
        # 3. 모든 변경사항 커밋
        db.session.commit()

        flash('추론 결과 및 관련 로그가 성공적으로 삭제 처리되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'결과 삭제 중 오류가 발생했습니다: {e}', 'danger')

    return redirect(url_for('iris.results'))

@iris.route('/logs')
@login_required
def logs():
    print("logs 시작")
    # UsageLog 모델은 변경사항이 없으므로 그대로 사용합니다.
    user_logs = UsageLog.query.filter_by(user_id=current_user.id).order_by(UsageLog.timestamp.desc()).all()
    print(f"user_logs: {user_logs}")
    return render_template('iris/user_logs.html', title='AI로그이력', results=user_logs)

@iris.route('/api/predict', methods=['POST'])
#@rate_limit('API_KEY_RATE_LIMIT')
@csrf.exempt
def api_predict():
    print("api_predict 시작")
    auth_header = request.headers.get('X-API-Key')
    if not auth_header:
        return jsonify({"error": "API Key is required"}), 401
    
    # API 키 검증 및 관련 정보 조회
    api_key_entry = APIKey.query.filter_by(key_string=auth_header, is_active=True).first()
    
    if not api_key_entry:
        return jsonify({"error": "Invalid or inactive API Key"}), 401
    
    # 'iris' 서비스 ID 조회 (API 요청 처리 전에 미리 조회)
    # 서비스 등록을 안했음으로 데이터가 없음(일단, comment 처리)
    #iris_service = Service.query.filter_by(servicename='iris').first()
    #if not iris_service:
    #    return jsonify({"error": "Iris service not found"}), 500
    
    #iris_service_id = iris_service.id
    iris_service_id = 1   # 임의로 설정

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    required_fields = ['sepal_length', 'sepal_width', 'petal_length', 'petal_width']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        sepal_length = float(data['sepal_length'])
        sepal_width = float(data['sepal_width'])
        petal_length = float(data['petal_length'])
        petal_width = float(data['petal_width'])
    except ValueError:
        return jsonify({"error": "Invalid data type for Iris features. Must be numbers."}), 400

    try:
        # 중복 레코드 확인
        existing_result = IrisResult.query.filter_by(
            sepal_length=sepal_length,
            sepal_width=sepal_width,
            petal_length=petal_length,
            petal_width=petal_width,
            user_id=api_key_entry.user_id
        ).first()

        # 중복 레코드가 있는 경우
        if existing_result:
            return jsonify({
                "message": "This prediction already exists.",
                "predicted_class": existing_result.predicted_class,
                "confirmed_class": existing_result.confirmed_class,
                "created_at": existing_result.created_at.isoformat() if existing_result.created_at else None,
                #"created_at": existing_result.created_at,
                "sepal_length": sepal_length,
                "sepal_width": sepal_width,
                "petal_length": petal_length,
                "petal_width": petal_width
            }), 200
            
        # 중복이 없는 경우, 새로운 레코드 생성

        features = np.array([[sepal_length, sepal_width, petal_length, petal_width]])
        #pred_index = model.predict(features)[0] - 1  # 모델 예측 결과는 1부터 시작하므로 -1
        pred_index = model.predict(features)[0]  # 모델 예측 결과는 0부터 시작
        predicted_class_name = TARGET_NAMES[pred_index]
        
        try:
            pred = model.predict(features)[0]
            print(f"예측 값 0부터 시작하는 지 확인: {pred}")  # pred는 0부터 시작
            # 1. 'iris' 서비스의 ID를 조회합니다.
            # 만약 서비스가 없으면 None으로 처리하거나 오류를 낼 수 있습니다.
            #iris_service = Service.query.filter_by(servicename='iris').first()   # Service 테이블의 servicename이 'iris'인 서비스 조회
            # 만약 서비스가 없으면 None이 될 수 있으므로, 이 부분을 수정
            #iris_service_id = iris_service.id if iris_service else None
            iris_service_id = 1   # 서비스 번호는 임의로 설정, 향후 다중 서비스인 경우, 해당 ID 할당 예정
            # 1. IrisResult 객체 생성
            new_iris_entry = IrisResult(
                user_id=api_key_entry.user_id,
                service_id=iris_service_id, # service_id 할당
                api_key_id=api_key_entry.id,
                sepal_length=sepal_length,
                sepal_width=sepal_width,
                petal_length=petal_length,
                petal_width=petal_width,
                predicted_class=predicted_class_name,
                model_version='1.0',
                confirmed_class=None,
                confirm=False,
                type='iris', # IrisResult에 type 컬럼이 있다면 추가
                redundancy=False # 중복이 아니므로 False로 설정
            )
            # logging
            current_app.logger.debug("new_iris_entry: %s", new_iris_entry)
            db.session.add(new_iris_entry)
            # 2. flush()를 통해 new_iris_entry의 ID를 미리 가져옵니다.
            #    아직 커밋은 하지 않아, 트랜잭션은 유지됩니다.
            db.session.flush() 

            print(f"new_iris_entry.id: {new_iris_entry.id}")
            # 3. UsageLog 객체 생성 시 위에서 얻은 ID를 사용합니다.
            # UsageLog 객체 생성
            new_usage_log = UsageLog(
                user_id=api_key_entry.user_id,
                service_id=iris_service_id, # service_id 할당
                api_key_id=api_key_entry.id,
                usage_type=UsageType.API_KEY,
                endpoint=request.path,
                inference_timestamp=datetime.now(), # 추론시각을 별도로 기록
                remote_addr=request.remote_addr,
                response_status_code=200,
                request_data_summary=str(data)[:200],
                prediction_result_id=new_iris_entry.id # 여기를 추가!
            )
            db.session.add(new_usage_log)
            # 4. 두 객체를 하나의 트랜잭션으로 한 번에 커밋합니다.
            db.session.commit()

            return jsonify({
                "predicted_class": predicted_class_name,
                "sepal_length": sepal_length,
                "sepal_width": sepal_width,
                "petal_length": petal_length,
                "petal_width": petal_width
            }), 200

        except Exception as e:
            # 오류 발생 시, 모든 변경 사항을 되돌립니다.
            db.session.rollback()

    except Exception as e:
        # 광범위한 예외 처리를 하나로 통합
        logging.error(f"Unexpected error in /api/predict (API Key): {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "An unexpected error occurred."}), 500

"""
@iris.route('/api/predict', methods=['POST'])
@csrf.exempt
def api_predict():
    print("api_predict 시작")
    auth_header = request.headers.get('X-API-Key')
    if not auth_header:
        return jsonify({"error": "API Key is required"}), 401
    
    # API 키 검증
    api_key_entry = APIKey.query.filter_by(key_string=auth_header, is_active=True).first()
    if not api_key_entry:
        return jsonify({"error": "Invalid or inactive API Key"}), 401
    
    # 'iris' 서비스 ID 조회
    iris_service = Service.query.filter_by(servicename='iris').first()
    if not iris_service:
        return jsonify({"error": "Iris service not found"}), 500
    
    iris_service_id = iris_service.id

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    required_fields = ['sepal_length', 'sepal_width', 'petal_length', 'petal_width']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        sepal_length = float(data['sepal_length'])
        sepal_width = float(data['sepal_width'])
        petal_length = float(data['petal_length'])
        petal_width = float(data['petal_width'])
    except ValueError:
        return jsonify({"error": "Invalid data type for Iris features. Must be numbers."}), 400

    try:
        # 중복 레코드 확인
        existing_result = IrisResult.query.filter_by(
            sepal_length=sepal_length,
            sepal_width=sepal_width,
            petal_length=petal_length,
            petal_width=petal_width,
            user_id=api_key_entry.user_id
        ).first()

        if existing_result:
            # 기존 결과를 재사용하는 경우에도 UsageLog를 남기는 것이 좋습니다.
            # 하지만 현재 코드에는 이 부분이 없어 추가하지 않았습니다.
            return jsonify({
                "message": "This prediction already exists.",
                "predicted_class": existing_result.predicted_class,
                "confirmed_class": existing_result.confirmed_class,
                "created_at": existing_result.created_at.isoformat() if existing_result.created_at else None,
                "sepal_length": sepal_length,
                "sepal_width": sepal_width,
                "petal_length": petal_length,
                "petal_width": petal_width
            }), 200

        # 중복이 없는 경우, 새로운 레코드 생성
        features = np.array([[sepal_length, sepal_width, petal_length, petal_width]])
        pred_index = model.predict(features)[0]
        
        # 인덱스 범위를 벗어나는 오류를 방지합니다.
        if pred_index >= len(TARGET_NAMES) or pred_index < 0:
            logging.error(f"Invalid prediction index: {pred_index}")
            return jsonify({"error": "Prediction model returned an invalid result."}), 500

        predicted_class_name = TARGET_NAMES[pred_index]
        
        # 데이터베이스 작업은 하나의 try 블록으로 묶습니다.
        new_iris_entry = IrisResult(
            user_id=api_key_entry.user_id,
            service_id=iris_service_id,
            api_key_id=api_key_entry.id,
            sepal_length=sepal_length,
            sepal_width=sepal_width,
            petal_length=petal_length,
            petal_width=petal_width,
            predicted_class=predicted_class_name,
            model_version='1.0',
            confirmed_class=None,
            confirm=False,
            type='iris',
            redundancy=False
        )
        db.session.add(new_iris_entry)
        db.session.flush()

        new_usage_log = UsageLog(
            user_id=api_key_entry.user_id,
            service_id=iris_service_id,
            api_key_id=api_key_entry.id,
            usage_type=UsageType.API_KEY,
            endpoint=request.path,
            inference_timestamp=datetime.now(),
            remote_addr=request.remote_addr,
            response_status_code=200,
            request_data_summary=str(data)[:200],
            prediction_result_id=new_iris_entry.id
        )
        db.session.add(new_usage_log)
        db.session.commit()

        return jsonify({
            "predicted_class": predicted_class_name,
            "sepal_length": sepal_length,
            "sepal_width": sepal_width,
            "petal_length": petal_length,
            "petal_width": petal_width
        }), 200

    except Exception as e:
        # 오류 발생 시 롤백하고 로깅 후 500 에러 반환
        db.session.rollback()
        logging.error(f"Error processing API request: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred. Please try again."}), 500
"""    
@iris.route('/confirms')
@login_required
def confirms():
    # confirmed_class가 None인 모든 예측 결과를 조회합니다.
    unconfirmed_results = PredictionResult.query.filter(
        PredictionResult.confirmed_class.is_(None)
    ).all()
    return render_template('iris/confirms.html', unconfirmed_results=unconfirmed_results)

@iris.route('/confirms/update', methods=['POST'])
@login_required
def update_confirm():
    try:
        # 폼 데이터에서 ID와 confirmed_class 값을 가져옵니다.
        prediction_id = request.form['id']
        confirmed_class_value = request.form['confirmed_class']

        # ID로 해당 PredictionResult 객체를 찾습니다.
        result_to_update = PredictionResult.query.get(prediction_id)

        if result_to_update:
            # confirmed_class와 confirm 필드를 업데이트합니다.
            result_to_update.confirmed_class = confirmed_class_value
            result_to_update.confirm = True
            db.session.commit()

    except Exception as e:
        print(f"Error updating prediction: {e}")
        db.session.rollback() # 오류 발생 시 롤백

    # 확인 페이지로 리다이렉트합니다.
    return redirect(url_for('iris.confirms'))

"""
윈도우 CMD
curl -X POST "http://localhost:5000/iris/api/predict" -H "Content-Type: application/json" -H "X-API-Key: your_api_key" -d "{\"sepal_length\":6.0,\"sepal_width\":3.5,\"petal_length\":4.5,\"petal_width\":1.5}"
윈도우 파워쉘
$headers = @{
    "Content-Type" = "application/json"
    "X-API-Key" = "your_api_key"
}

$body = @{
    sepal_length = 6.0
    sepal_width = 3.5
    petal_length = 4.5
    petal_width = 1.5
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5000/iris/api/predict" -Method Post -Headers $headers -Body $body

"""

