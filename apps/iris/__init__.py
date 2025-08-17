#apps/iris/__init__.py
from flask import Blueprint

iris = Blueprint('iris', __name__, template_folder='templates')

from . import views  # views.py import해서 라우팅 등록
