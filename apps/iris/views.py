# apps/iris/views.py
from flask import Flask, flash, redirect, request, render_template, jsonify, abort, current_app, url_for, g
import pickle, os
import logging, functools
from sqlalchemy import desc, func
from apps.extensions import csrf
from apps.dbmodels import PredictionResult, db, APIKey, UsageLog, UsageType, Service, Match, UserType, MatchStatus
from apps.iris.dbmodels import IrisResult
import numpy as np
from flask_login import current_user, login_required
from apps.iris.forms import EmptyForm, IrisUserForm
from . import iris
from datetime import datetime, timedelta
# 데코레이터 import 추가
from apps.decorators import admin_required, expert_required


MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model.pkl')
with open(MODEL_PATH, 'rb') as f:
    model = pickle.load(f)

TARGET_NAMES = ['setosa', 'versicolor', 'virginica']
from apps.config import Config

@iris.route('/services')
def services():
    current_app.logger.debug("search_query: %s", "Starts services")
    return render_template('iris/services.html')

@iris.route('/iris_predict', methods=['GET', 'POST'])
@login_required
def iris_predict():
    form = IrisUserForm()
    if form.validate_on_submit():
        sepal_length = form.sepal_length.data
        sepal_width = form.sepal_width.data
        petal_length = form.petal_length.data
        petal_width = form.petal_width.data
       
        features = np.array([[sepal_length, sepal_width, petal_length, petal_width]])

        existing_result = IrisResult.query.filter_by(
            sepal_length=sepal_length,
            sepal_width=sepal_width,
            petal_length=petal_length,
            petal_width=petal_width,
            #user_id=current_user.id  # 자신만 중복 체크
        ).first()

        if existing_result:
            flash("이미 존재하는 값입니다. 기존 예측 결과를 표시합니다.", 'info')

            return render_template('iris/predict.html',
                                   result=existing_result.predicted_class,
                                   sepal_length=sepal_length,
                                   sepal_width=sepal_width,
                                   petal_length=petal_length,
                                   petal_width=petal_width,
                                   form=form,
                                   TARGET_NAMES=TARGET_NAMES,
                                   iris_result_id=existing_result.id,
                                   allow_confirm_save=False) 

        else:
            pred = model.predict(features)[0]
            iris_service_id = 1   

            new_iris_result = IrisResult(
                user_id=current_user.id,
                service_id=iris_service_id,  
                sepal_length=sepal_length,
                sepal_width=sepal_width,
                petal_length=petal_length,
                petal_width=petal_width,
                predicted_class=TARGET_NAMES[pred],  
                model_version='1.0',  
                confirm=False  
            )
            db.session.add(new_iris_result)
            db.session.flush() 
            new_usage_log = UsageLog(
                user_id=current_user.id,
                usage_type=UsageType.WEB_UI,
                endpoint=request.path,
                remote_addr=request.remote_addr,
                response_status_code=200,
                inference_timestamp=datetime.now(), 
                service_id=iris_service_id, 
                prediction_result_id=new_iris_result.id 
            )
            db.session.add(new_usage_log)
            db.session.commit()
            iris_result_id = new_iris_result.id
            return render_template('iris/predict.html',
                                result=TARGET_NAMES[pred],
                                sepal_length=sepal_length, sepal_width=sepal_width,
                                petal_length=petal_length, petal_width=petal_width, form=form,
                                TARGET_NAMES=TARGET_NAMES, iris_result_id=iris_result_id,
                                allow_confirm_save=True)
    return render_template('iris/predict.html', form=form)

@iris.route('/save_iris_data', methods=['POST'])
@login_required
def save_iris_data():
    if request.method != 'POST':
        flash('잘못된 접근입니다.', 'danger')
        return redirect(url_for('iris.iris_predict'))

    result_id = request.form.get('iris_result_id')
    confirmed_class = request.form.get('confirmed_class')

    if not result_id or confirmed_class not in ['setosa', 'versicolor', 'virginica']:
        flash('유효한 데이터 ID 또는 품종이 아닙니다.', 'danger')
        return redirect(url_for('iris.iris_predict'))

    try:
        result = IrisResult.query.filter_by(id=result_id).first_or_404()
        if result.user_id != current_user.id:
            abort(403)
        result.confirmed_class = confirmed_class
        result.confirm = True
        result.confirmed_at = datetime.now()
        recent_log = UsageLog.query.filter_by(prediction_result_id=result.id).order_by(desc(UsageLog.timestamp)).first()
       
        new_usage_log = UsageLog(
            user_id=current_user.id,
            service_id=recent_log.service_id if recent_log else None,
            api_key_id=recent_log.api_key_id if recent_log else None,
            endpoint=request.path,
            usage_type=UsageType.WEB_UI,
            log_status='추론확인',
            inference_timestamp=recent_log.inference_timestamp if recent_log else None,
            remote_addr=request.remote_addr,
            response_status_code=200,
            prediction_result_id=result.id
        )
        db.session.add(new_usage_log)

        db.session.commit()

        flash('추론 확인 및 관련 로그가 성공적으로 처리되었습니다.', 'success')
        return redirect(url_for('iris.iris_predict'))

    except Exception as e:
        db.session.rollback()
        flash(f'결과 입력 중 오류가 발생했습니다: {e}', 'danger')
        return redirect(url_for('iris.iris_predict'))

# 수정된 results() 함수
@iris.route('/results')
@login_required
def results():
    search_query = request.args.get('search', '', type=str)
    confirm_query = request.args.get('confirm', '', type=str)
    date_filter_type = request.args.get('date_filter_type', '', type=str)
    start_date_str = request.args.get('start_date', '', type=str)
    end_date_str = request.args.get('end_date', '', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # 쿼리 기본 설정
    query = IrisResult.query

    # 사용자 권한에 따른 필터링 로직
    if current_user.is_admin():
        pass # 관리자는 모든 결과를 볼 수 있음
    elif current_user.is_expert():
        # 전문가와 매칭된 사용자 ID 목록 가져오기
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id, status=MatchStatus.IN_PROGRESS).all()]
        query = query.filter(
            (IrisResult.user_id.in_(matched_user_ids)) | (IrisResult.user_id == current_user.id)
        )
    else: # 일반 사용자
        query = query.filter_by(user_id=current_user.id)

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

    if has_date_filter_error:
        # 오류가 발생한 경우 빈 결과를 반환
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
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
        )

    if search_query:
        query = query.filter(
            (IrisResult.predicted_class.ilike(f'%{search_query}%')) |
            (IrisResult.confirmed_class.ilike(f'%{search_query}%'))
        )

    if confirm_query:
        if confirm_query == 'true':
            query = query.filter(IrisResult.confirm == True)
        elif confirm_query == 'false':
            query = query.filter(IrisResult.confirm == False)

    query = query.order_by(IrisResult.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    user_results = pagination.items
    form = EmptyForm() 

    return render_template(
        'iris/user_results.html',
        title='추론결과',
        results=user_results,
        form=form,
        pagination=pagination,
        search_query=search_query,
        confirm_query=confirm_query,
        date_filter_type=date_filter_type,
        start_date=start_date_str,
        end_date=end_date_str,
    )

# 수정된 confirm_result() 함수
@iris.route('/confirm_result/<int:result_id>', methods=['POST'])
@login_required
def confirm_result(result_id):
    result = IrisResult.query.get_or_404(result_id)
    # 권한 확인
    if current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id).all()]
        if result.user_id not in matched_user_ids:
            flash('다른 사용자의 결과를 확인 할 수 없습니다.', 'danger')
            abort(403)
    elif not current_user.is_admin() and result.user_id != current_user.id:
        flash('다른 사용자의 결과를 확인 할 수 없습니다.', 'danger')
        abort(403)

    confirmed_class = request.form.get('confirmed_class')
    if confirmed_class in ['setosa', 'versicolor', 'virginica']:
        result.confirmed_class = confirmed_class
        result.confirm = True
        result.confirmed_at = datetime.now()
        db.session.flush()                       
        try:
            recent_log = (
                UsageLog.query
                .filter_by(prediction_result_id=result.id)  
                .order_by(desc(UsageLog.timestamp))      
                .first()                                 
            )
            print(f"recent_log: {recent_log}")
       
            if recent_log:
                print(f"Recent log found: {recent_log.timestamp}")
            else:
                print("No logs found for this prediction_result_id.")
    
            new_usage_log = UsageLog(
                #user_id=recent_log.user_id,     
                user_id=current_user.id,     
                service_id=recent_log.service_id, 
                api_key_id=recent_log.api_key_id, 
                endpoint=request.path,            
                usage_type=UsageType.WEB_UI,
                log_status='추론확인',             
                inference_timestamp=recent_log.inference_timestamp, 
                remote_addr=request.remote_addr,   
                response_status_code = 200,
                prediction_result_id=recent_log.prediction_result_id 
            )
            db.session.add(new_usage_log)
            db.session.commit()
            flash('추론 확인 및 관련 로그가 성공적으로 처리되었습니다.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'결과 입력 중 오류가 발생했습니다: {e}', 'danger')
    else:
        flash('유효하지 않은 품종입니다.', 'danger')
    return redirect(url_for('iris.results'))

# 수정된 edit_confirmed_class() 함수
@iris.route('/edit_confirmed_class/<int:result_id>', methods=['POST'])
@login_required
def edit_confirmed_class(result_id):
    # 권한 확인
    result = IrisResult.query.get_or_404(result_id)
    if current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id).all()]
        if result.user_id not in matched_user_ids and result.user_id != current_user.id:
            flash('다른 사용자의 결과를 수정 할 수 없습니다.', 'danger')
            abort(403)
    elif not current_user.is_admin() and result.user_id != current_user.id:
        flash('다른 사용자의 결과를 수정 할 수 없습니다.', 'danger')
        abort(403)
        
    form = EmptyForm() 
    if form.validate_on_submit(): 
        confirmed_class = request.form.get('confirmed_class')
        if confirmed_class in ['setosa', 'versicolor', 'virginica']:
            try:
                result.confirmed_class = confirmed_class
                result.confirmed_at = datetime.now()
                db.session.commit()
                recent_log = UsageLog.query.filter_by(prediction_result_id=result.id).order_by(desc(UsageLog.timestamp)).first()
                if recent_log:
                    new_usage_log = UsageLog(
                        user_id=current_user.id,     
                        service_id=recent_log.service_id,
                        api_key_id=recent_log.api_key_id,
                        endpoint=request.path,
                        usage_type=UsageType.WEB_UI,
                        log_status='추론수정',  
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

"""
HARD DELETE 
# 수정된 delete_result() 함수
@iris.route('/delete_result/<int:result_id>', methods=['POST'])
@login_required
def delete_result(result_id):
    result = IrisResult.query.get_or_404(result_id)
    
    # 권한 확인
    if current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id).all()]
        if result.user_id not in matched_user_ids and result.user_id != current_user.id:
            flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
            abort(403)
    elif not current_user.is_admin() and result.user_id != current_user.id:
        flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
        abort(403)

    try:
        # 1. soft-delete 로 변경 필요
        # 2. 과거 존재한 모든 log에 대해 삭제로 처리함 -> 이번 것만 삭제로 처리, 나머지는 그대로 
        related_logs = UsageLog.query.filter_by(prediction_result_id=result.id).all()
        for log in related_logs:
            log.log_status = "삭제"
            log.inference_stamp = log.timestamp 
            log.timestamp = datetime.now() 
        db.session.delete(result)
        db.session.commit()
        flash('추론 결과 및 관련 로그가 성공적으로 삭제 처리되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'결과 삭제 중 오류가 발생했습니다: {e}', 'danger')
    return redirect(url_for('iris.results'))
"""

# 수정된 delete_result() 함수  SOFT-DELETE
@iris.route('/delete_result/<int:result_id>', methods=['POST'])
@login_required
def delete_result(result_id):
    result = IrisResult.query.get_or_404(result_id)
    
    # 권한 확인 (기존 로직 유지)
    if current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id).all()]
        if result.user_id not in matched_user_ids and result.user_id != current_user.id:
            flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
            abort(403)
    elif not current_user.is_admin() and result.user_id != current_user.id:
        flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
        abort(403)

    try:
        # soft-delete 적용: is_deleted 필드를 True로 변경
        result.is_deleted = True
        db.session.commit()

        # 삭제 로그만 새로 생성 (기존 로그는 변경하지 않음)
        # 삭제 로그에 필요한 이전 정보 가져오기
        recent_log = UsageLog.query.filter_by(prediction_result_id=result.id).order_by(desc(UsageLog.timestamp)).first()
        if recent_log:
            new_usage_log = UsageLog(
                user_id=current_user.id,
                service_id=recent_log.service_id,
                api_key_id=recent_log.api_key_id,
                endpoint=request.path,
                usage_type=UsageType.WEB_UI,
                log_status='삭제',  
                inference_timestamp=recent_log.inference_timestamp,
                remote_addr=request.remote_addr,
                response_status_code=200,
                prediction_result_id=result.id
            )
            db.session.add(new_usage_log)
            db.session.commit()
       
        flash('추론 결과가 성공적으로 삭제 처리되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'결과 삭제 중 오류가 발생했습니다: {e}', 'danger')
    return redirect(url_for('iris.results'))

# 수정된 logs() 함수
@iris.route('/logs')
@login_required
def logs():
    # 사용자 권한에 따른 로그 조회 범위 설정 수정
    if current_user.is_admin():
        user_logs = UsageLog.query.order_by(UsageLog.timestamp.desc()).all()
    elif current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id, status=MatchStatus.IN_PROGRESS).all()]
        #print(matched_user_ids)
        user_logs = UsageLog.query.filter(
            (UsageLog.user_id.in_(matched_user_ids)) | (UsageLog.user_id == current_user.id)
        ).order_by(UsageLog.timestamp.desc()).all()
    else: # 일반 사용자
        user_logs = UsageLog.query.filter_by(user_id=current_user.id).order_by(UsageLog.timestamp.desc()).all()

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
            #user_id=api_key_entry.user_id  # 자신만 중복 체크
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