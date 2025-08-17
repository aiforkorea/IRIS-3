from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from . import iris
from apps.mypage.forms import ApiKeyForm, ChangePasswordForm
from apps import db
from apps.dbmodels import APIKey, User
@iris.route('/services')
def services():
    return render_template('iris/services.html')
