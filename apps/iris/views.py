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
            user_id=current_user.id 
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
                user_id=recent_log.user_id,     
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
        if result.user_id not in matched_user_ids:
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
                        user_id=recent_log.user_id,
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

# 수정된 delete_result() 함수
@iris.route('/delete_result/<int:result_id>', methods=['POST'])
@login_required
def delete_result(result_id):
    result = IrisResult.query.get_or_404(result_id)
    
    # 권한 확인
    if current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id).all()]
        if result.user_id not in matched_user_ids:
            flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
            abort(403)
    elif not current_user.is_admin() and result.user_id != current_user.id:
        flash('다른 사용자의 결과를 삭제할 수 없습니다.', 'danger')
        abort(403)

    try:
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

# 수정된 logs() 함수
@iris.route('/logs')
@login_required
def logs():
    # 사용자 권한에 따른 로그 조회 범위 설정 수정
    if current_user.is_admin():
        user_logs = UsageLog.query.order_by(UsageLog.timestamp.desc()).all()
    elif current_user.is_expert():
        matched_user_ids = [m.user_id for m in Match.query.filter_by(expert_id=current_user.id).all()]
        user_logs = UsageLog.query.filter(
            (UsageLog.user_id.in_(matched_user_ids)) | (UsageLog.user_id == current_user.id)
        ).order_by(UsageLog.timestamp.desc()).all()
    else: # 일반 사용자
        user_logs = UsageLog.query.filter_by(user_id=current_user.id).order_by(UsageLog.timestamp.desc()).all()

    return render_template('iris/user_logs.html', title='AI로그이력', results=user_logs)