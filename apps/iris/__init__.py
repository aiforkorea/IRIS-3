# apps/iris/__init__.py
from flask import Blueprint

iris = Blueprint('iris', __name__, template_folder='templates')
# iris 블루프린트 생성, static 폴더는 apps/static/iris에 위치함
# iris 블루프린트 생성, templates 폴더는 apps/templates/iris에 위치함

from . import views  # views.py import해서 라우팅 등록
#from . import errors  # errors.py import해서 에러 핸들러 등록
#from . import forms  # forms.py import해서 폼 등록
