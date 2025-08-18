from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from . import mypage
from apps.mypage.forms import ApiKeyForm, ChangePasswordForm
from apps import db
from apps.dbmodels import APIKey, User
@mypage.route('/dashboard')
@login_required
def dashboard():
    total_api_keys = APIKey.query.filter_by(user_id=current_user.id).count()
    approved_subscriptions = 2 #Subscription.query.filter_by(user_id=current_user.id, status='approved').count()
    pending_subscriptions = 1 #Subscription.query.filter_by(user_id=current_user.id, status='pending').count() 
    # 최근 사용 로그 5개
    recent_usage_logs = None
    # UsageLog.query.filter_by(user_id=current_user.id)\
    #                                .order_by(UsageLog.timestamp.desc())\
    #                                .limit(5).all()
    # 이번 달 총 사용량
    current_month = datetime.now().month
    current_year = datetime.now().year
    monthly_usage = 0
    #db.session.query(func.sum(UsageLog.usage_count))\
    #                    .filter(UsageLog.user_id == current_user.id)\
    #                    .filter(extract('month', UsageLog.timestamp) == current_month)\
    #                    .filter(extract('year', UsageLog.timestamp) == current_year)\
    #                    .scalar() or 0
    return render_template('mypage/dashboard.html',
                           title='마이페이지 대시보드',
                           total_api_keys=total_api_keys,
                           approved_subscriptions=approved_subscriptions,
                           pending_subscriptions=pending_subscriptions,
                           recent_usage_logs=recent_usage_logs,
                           monthly_usage=monthly_usage) 
# change_password 엔드포인트
@mypage.route("/change_password", methods=["GET", "POST"])
@login_required  # 로그인한 사용자만 접근 가능
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = User.query.get(current_user.id)
        if user.verify_password(form.current_password.data):
            user.password = form.new_password.data
            db.session.commit()
            flash("비밀번호가 성공적으로 변경되었습니다.")
            return redirect(url_for("mypage.dashboard"))
        else:
            flash("현재 비밀번호가 올바르지 않습니다.")
    return render_template("mypage/change_password.html", form=form)
@mypage.route('/api_keys')    # 키 조회
@login_required
def api_keys():
    # 1. Create an instance of your form
    form = ApiKeyForm()
    if form.validate_on_submit():
        # Handle form submission, e.g., generate a new API key
        # For demonstration, let's just show a message
        flash('Form submitted successfully!', 'success')
        # You'd typically generate and save a new API key here
        # Example:
        # new_key_value = "some_random_key_generated"
        # new_api_key = ApiKey(user_id=current_user.id, key=new_key_value)
        # db.session.add(new_api_key)
        # db.session.commit()
        return redirect(url_for('mypage.api_keys')) # Redirect to prevent form resubmission
    user_api_keys = APIKey.query.filter_by(user_id=current_user.id).order_by(APIKey.created_at.desc()).all()
    # 2. Pass the form instance to the template
    return render_template('mypage/api_keys.html',
                           title='API Keys',
                           api_keys=user_api_keys,
                           form=form) 
@mypage.route('/api_keys/generate', methods=['POST'])
@login_required
def generate_api_key():
    # 사용자별 API 키 생성 개수 제한 등을 추가할 수 있습니다.
    existing_keys_count = APIKey.query.filter_by(user_id=current_user.id).count()
    if existing_keys_count >= 5: # 예시: 사용자당 5개로 제한
        flash('API Key는 최대 5개까지 발급할 수 있습니다.', 'warning')
        return redirect(url_for('mypage.api_keys'))

    new_key = APIKey(user_id=current_user.id)
    new_key.generate_key()
    db.session.add(new_key)
    db.session.commit()
    flash(f'새로운 API Key가 발급되었습니다: {new_key.key_string}', 'success')
    return redirect(url_for('mypage.api_keys'))
@mypage.route('/toggle-api-key/<int:key_id>', methods=['POST'])
@login_required
def toggle_api_key_active(key_id):
    api_key = APIKey.query.get_or_404(key_id)

    # 현재 사용자가 해당 API 키의 소유자인지 확인하는 로직 (중요!)
    if api_key.user_id != current_user.id:
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('mypage.api_keys'))

    api_key.is_active = not api_key.is_active # 상태 토글
    db.session.commit()
    flash(f"API 키 {'활성화' if api_key.is_active else '비활성화'} 완료.", 'success')
    return redirect(url_for('mypage.api_keys'))
@mypage.route('/delete-api-key/<int:key_id>', methods=['POST'])
@login_required
def delete_api_key(key_id):
    api_key = APIKey.query.get_or_404(key_id)
    # 현재 사용자가 해당 API 키의 소유자인지 확인하는 로직 (중요!)
    if api_key.user_id != current_user.id:
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('mypage.api_keys'))
    try:
        db.session.delete(api_key) # API 키 삭제
        db.session.commit()
        flash('API 키가 성공적으로 삭제되었습니다.', 'success')
    except Exception as e:
        db.session.rollback() # 오류 발생 시 롤백
        flash(f'API 키 삭제 중 오류가 발생했습니다: {e}', 'danger')
    return redirect(url_for('mypage.api_keys'))
