# apps/__init__.py
import logging
from logging.handlers import RotatingFileHandler   # logging 추가
from flask import Flask
from werkzeug.security import generate_password_hash
from .extensions import db, migrate, login_manager, csrf
from .config import Config
from apps.dbmodels import UsageType, UserType, User

# 전역 변수/인스턴스 초기화 (extensions.py에서 정의)
def create_app():   # factory 함수
    app = Flask(__name__)
    app.config.from_object(Config)
    # 로깅 설정
    if app.debug:  # 개발 환경에서는 콘솔에만 로깅 (디버그 모드에서만)
        app.logger.setLevel(logging.DEBUG)
    else: # 프로덕션 환경에서는 파일에 로깅
        file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter( '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]' )) 
        file_handler.setLevel(logging.INFO) 
        app.logger.addHandler(file_handler) 
        app.logger.setLevel(logging.INFO)
    # 확장 기능 초기화 연계
    db.init_app(app)                      # flask 앱에 db연결
    migrate.init_app(app,db)              # 없으면, flask db 명령어를 사용불가
    login_manager.init_app(app)  # flask 앱에 로그인 관리 연결
    csrf.init_app(app)                    # flask 앱에 CSRF 보호 연결 

    # Flask-Login: 사용자 로더 설정 (auth 블루프린트에서 import하여 사용)
    # create_app() 정의 또는 auth/__init__.py 정의하여 login_manager.user_loader 데코레이터와 함께 사용
    from .dbmodels import User  # User 모델 임포트
    @login_manager.user_loader
    def load_user(user_id):   # Flask-Login이 user_id를 기반으로 사용자 객체를 로드
        return User.query.get(int(user_id))
        # UUID를 사용시 int() 변환을 제거합니다.
        # return User.query.get(user_id)
    # Flask-Login: Unauthorized Error 핸들링, login_view와 같은 기능이나, next 값 자동전달
    @login_manager.unauthorized_handler
    def unauthorized():
        """로그인되지 않은 사용자가 @login_required 페이지에 접근 시 redirect"""
        from flask import flash, redirect, url_for, request
        flash('로그인이 필요합니다.', 'warning')
        return redirect(url_for('auth.login', next=request.path))
    # 모든 템플릿에 'UserType' 변수를 추가합니다.
    @app.context_processor
    def inject_user_type():
        return {'UserType': UserType}

    # UserLogType 도 추가해야 하는지 검토

    # 모든 템플릿에 "UsageType" 변수를 추가합니다.
    @app.context_processor
    def inject_usage_type():
        return {"UsageType": UsageType}

    # 블루프린트 등록  -- mypage모듈이 없으므로 현재 오류 발생(mypage 설치후 오류 없어짐)
    from .main import main
    from .auth import auth
    from .admin import admin
    from .mypage import mypage
    from .iris import iris

    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(admin, url_prefix="/admin")
    app.register_blueprint(mypage, url_prefix="/mypage")
    app.register_blueprint(iris, url_prefix="/iris")

    # db 테이블 생성 및 관리자 초기계정 생성
    with app.app_context():
        db.drop_all()         # 운영시에는 커멘트 처리 필요
        db.create_all()       # 테이블 생성
        # 최초 관리자 계정 생성
        admin_username = app.config.get('ADMIN_USERNAME')
        admin_email = app.config.get('ADMIN_EMAIL')
        admin_password = app.config.get('ADMIN_PASSWORD')

        if admin_username and admin_password:
            admin_user = User.query.filter_by(username=admin_username).first()
            if not admin_user:
                hashed_password = generate_password_hash(admin_password)
                new_admin = User(username=admin_username, email=admin_email, password_hash=hashed_password, user_type=UserType.ADMIN)  # ADMIN 설정. is_admin=True 삭제
                db.session.add(new_admin)
                db.session.commit()
                print(f"관리자 계정 '{admin_username}', '{admin_password}' 이(가) 생성되었습니다.")
            else:
                print(f"관리자 계정 '{admin_username}'이(가) 이미 존재합니다.")
        else:
            print("ADMIN_USERNAME 또는 ADMIN_PASSWORD 환경 변수가 설정되지 않았습니다.")
        return app
