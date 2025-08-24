# apps/match/__init__.py
from flask import Blueprint

# Blueprint 객체 생성
match = Blueprint('match', __name__, template_folder='templates')

# 이제 Blueprint 객체가 생성되었으므로 views 모듈을 안전하게 가져올 수 있습니다.
# views 모듈은 별도로 match 객체를 다시 import할 필요 없음.
from . import views