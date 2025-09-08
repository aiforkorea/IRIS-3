# apps/decorators.py
from datetime import datetime, timedelta
import functools, logging
from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user
from apps.config import Config
from apps.dbmodels import User
# 관리자 권한 확인 데코레이터
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('관리자 권한이 필요합니다.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function
# 전문가 권한 확인 데코레이터
# 추가
def expert_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_expert():
            flash('전문가 권한이 필요합니다.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

# 추가
def user_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_user():
            flash('일반사용자 권한이 필요합니다.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function
