# apps/dbmodels.py
import enum, uuid
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from apps.extensions import db
from enum import Enum

class UserType(enum.Enum):  # 사용자 구분(순서 중요)
    USER = "user"
    EXPERT = "expert"
    ADMIN = "admin"

    @classmethod    # 권고
    def has_value(cls, value):
        """
        Enum에 입력된 값이 유효한지 확인합니다.
        """
        return value in cls._value2member_map_  # Enum의 모든 값 리스트를 검색

class UserLogType(enum.Enum):  # 사용자 로그 구분
    ACCOUNT_STATUS_CHANGE = "계정상태변경"
    USER_ROLE_CHANGE = "사용자역할변경"
    USER_INFO_MODIFY = "사용자정보수정"
    USER_ERASE = "사용자삭제"
    USER_CREATE = "사용자생성"
    @classmethod     # 권고
    def has_value(cls, value):
        """
        Enum에 입력된 값이 유효한지 확인합니다.
        """
        return value in cls._value2member_map_  # Enum의 모든 값 리스트를 검색

class UsageType(enum.Enum):
    LOGIN = "login"
    API_KEY = "api_key"
    WEB_UI = "web_ui"
    @classmethod      # 권고
    def has_value(cls, value):
        """
        Enum에 입력된 값이 유효한지 확인합니다.
        """
        return value in cls._value2member_map_  # Enum의 모든 값 리스트를 검색

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, index=True)
    email = db.Column(db.String, unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    user_type = db.Column(db.Enum(UserType), nullable=False, default=UserType.USER)
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    usage_count = db.Column(db.Integer, default=0)
    daily_limit = db.Column(db.Integer, default=1000)
    monthly_limit = db.Column(db.Integer, default=5000)
    created_at = db.Column(db.DateTime, default=func.now())
    updated_at = db.Column(db.DateTime, default=func.now(), onupdate=func.now())
    # [수정] backref 대신 back_populates를 사용하여 양방향 관계를 명시적으로 설정
    action_logs = db.relationship('Log', foreign_keys='Log.user_id', back_populates='actor', lazy='dynamic')
    targeted_logs = db.relationship('Log', foreign_keys='Log.target_user_id', back_populates='target_user', lazy='dynamic')
    # 연관된 로그 (User가 삭제될 때 관련 로그는 유지)
    api_keys = db.relationship("APIKey", back_populates="user", lazy=True, cascade="all, delete-orphan")
    usage_logs = db.relationship("UsageLog", back_populates="user", lazy=True, cascade="all, delete-orphan")
    subscriptions=db.relationship("Subscription", back_populates="user", lazy=True, cascade="all, delete-orphan")
    prediction_results = db.relationship("PredictionResult", back_populates="user", lazy=True, cascade="all, delete-orphan")

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    def verify_password(self, password):
        if self.password_hash is None:
            return False
        return check_password_hash(self.password_hash, password)
    def is_admin(self):
        return self.user_type == UserType.ADMIN
    def is_expert(self):
        return self.user_type == UserType.EXPERT
    def is_user(self):
        return self.user_type == UserType.USER
    # [수정] 이메일 중복 체크 로직 수정
    def is_duplicate_email(self):
        query = User.query.filter_by(email=self.email)
        # 만약 self.id가 존재한다면 (즉, 이미 데이터베이스에 저장된 사용자라면)
        # 자기 자신은 중복 체크에서 제외해야 함
        if self.id:
            query = query.filter(User.id != self.id)
        return query.first() is not None

    def soft_delete(self):
        """
        사용자를 soft-delete 처리합니다.
        실제 데이터를 삭제하는 대신, is_deleted 플래그를 True로,
        is_active 플래그를 False로 설정합니다.
        """
        self.is_deleted = True
        self.is_active = False

#    user_type 필드가 유효한 값을 가졌는지 검증합니다.
#    @validates("user_type")   # 권고
#    def validate_user_type(self, key, value):
#        if not UserType.has_value(value):
#            raise ValueError(f"Invalid user_type: {value}. Must be one of: {[e.value for e in UserType]}")
#        return value

    def __repr__(self):
        return f'<User {self.username}>'


class Log(db.Model):
    __tablename__ = "logs"
    id = db.Column(db.Integer, primary_key=True)
    
    # 외래 키 정의는 그대로 유지
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, comment="행위를 수행한 사용자 ID")
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, comment="행위의 대상이 된 사용자 ID")
    
    # [수정] backref 대신 back_populates를 사용하고, 상대편 모델의 속성 이름을 정확히 지정
    actor = db.relationship('User', foreign_keys=[user_id], back_populates='action_logs')
    target_user = db.relationship('User', foreign_keys=[target_user_id], back_populates='targeted_logs')
    
    endpoint = db.Column(db.String(120), nullable=False)
    log_title = db.Column(db.String(50), nullable=False)
    log_summary = db.Column(db.Text)
    
    timestamp = db.Column(db.DateTime, default=func.now(), index=True)
    remote_addr = db.Column(db.String(45))
    response_status_code = db.Column(db.Integer)

    def __repr__(self) -> str:
        return f"<Log(user_id={self.user_id}, target_user_id={self.target_user_id}, log_title='{self.log_title}')>"

class Service(db.Model):
    __tablename__ = "services"
    id = db.Column(db.Integer, primary_key=True)
    servicename = db.Column(db.String(100), unique=True, nullable=False)
    is_active=db.Column(db.Boolean, default=True)  # 활성화 여부
    is_auto=db.Column(db.Boolean, default=True)  # 자동승인 여부
    price = db.Column(db.Integer, default=0, nullable=False)  # 서비스 단가
    description = db.Column(db.Text, nullable=False)
    keywords = db.Column(db.String(200), nullable=False)
    service_endpoint = db.Column(db.String(255), nullable=True)  # 서비스 엔드포인트 함수, 일단 True
    created_at=db.Column(db.DateTime, default=func.now())
    updated_at=db.Column(db.DateTime, default=func.now(), onupdate=func.now())

    # 관계
    subscriptions = db.relationship('Subscription', back_populates='service', lazy=True, cascade="all, delete-orphan")
    usage_logs = db.relationship('UsageLog', back_populates='service', lazy=True, cascade="all, delete-orphan")
    prediction_results = db.relationship('PredictionResult', back_populates='service', lazy=True, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Service(name='{self.servicename}')>" # servicename으로 변경

class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False) 
    status = db.Column(db.String(20), default='pending', nullable=False) # pending, approved, rejected
    request_date = db.Column(db.DateTime, nullable=False, default=func.now())
    approval_date = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', back_populates='subscriptions')
    service = db.relationship('Service', back_populates='subscriptions')
    # 한 사용자가 특정 서비스를 여러 번 구독 요청하지 못하도록 제약하는 방식
    __table_args__ = (db.UniqueConstraint('user_id', 'service_id', name='_user_service_uc'),)

    def __repr__(self) -> str:
        return f"<Subscription(user_id={self.user_id}, service_id={self.service_id}, status='{self.status}')>"

class APIKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    key_string = db.Column(db.String(32), unique=True, nullable=False, default=lambda: str(uuid.uuid4()).replace('-', '')[:32])
    description = db.Column(db.String(100), nullable=True)
    user_id=db.Column(db.Integer, db.ForeignKey('users.id'), index=True, comment="Key 소유 사용자ID")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=func.now())
    last_used = db.Column(db.DateTime, default=func.now(), onupdate=func.now())
    usage_count = db.Column(db.Integer, default=0) # 이 API 키를 통한 총 사용 횟수
    daily_limit = db.Column(db.Integer, default=1000)
    monthly_limit = db.Column(db.Integer, default=5000) 

    user = db.relationship("User", back_populates="api_keys")
    usage_logs = db.relationship('UsageLog', back_populates='api_key', lazy=True)
    prediction_results = db.relationship("PredictionResult", back_populates="api_key", lazy=True, cascade="all, delete-orphan")
    def generate_key(self) -> None:
        self.key_string = str(uuid.uuid4()).replace('-', '')[:32]
    def __repr__(self) -> str:
        return f"<APIKey(key_string='{self.key_string}')>"

class UsageLog(db.Model):
    __tablename__ = "usage_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id=db.Column(db.Integer, db.ForeignKey('users.id'), index=True, comment="행위 수행 사용자ID")
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    api_key_id=db.Column(db.Integer,db.ForeignKey('api_keys.id'),index=True, nullable=True, comment="KEY ID") 
    endpoint = db.Column(db.String(120), nullable=False)
    usage_type = db.Column(db.Enum(UsageType), nullable=False)
    log_status = db.Column(db.String(10), default="추론", nullable=False) # '추론', '삭제', '로그인' 등

    usage_count = db.Column(db.Integer, default=1, nullable=False) # 각 로그 항목은 기본적으로 1회 사용
    login_confirm = db.Column(db.String(10), nullable=True) # 로그인 여부 확인용 (예: 'success', 'fail')
    inference_timestamp = db.Column(db.DateTime, index=True)  # 추론 시각

    timestamp = db.Column(db.DateTime, default=func.now(), index=True)
    last_used = db.Column(db.DateTime, default=func.now(), onupdate=func.now()) # 마지막 사용 시간
    remote_addr = db.Column(db.String(45))
    request_data_summary = db.Column(db.Text)
    response_status_code = db.Column(db.Integer)
    # (추론 ID)새로 추가될 부분: 어떤 PredictionResult/IrisResult와 관련된 로그인지 저장
    prediction_result_id = db.Column(db.Integer, db.ForeignKey('iris_results.id'), nullable=True, index=True) # IrisResult 테이블명에 맞게 수정

    user = db.relationship('User', back_populates='usage_logs')
    api_key = db.relationship('APIKey', back_populates='usage_logs')
    service = db.relationship('Service', back_populates='usage_logs')
    def __repr__(self) -> str:
        return f"<UsageLog(service_id={self.service_id}, usage_type='{self.usage_type}', timestamp={self.timestamp})>"

# ----------- 예측 결과 기본 모델 (PredictionResult) -----------
class PredictionResult(db.Model):
    __tablename__ = "prediction_results"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), index=True, nullable=True)
    predicted_class = db.Column(db.String(50))
    model_version = db.Column(db.String(20), default='1.0')
    confirmed_class = db.Column(db.String(50))
    confirm = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=func.now(), index=True)
    confirmed_at = db.Column(db.DateTime, index=True)  # default=datetime.now 설정하면 안됨

    # 다형성 설정: 어떤 예측 결과 유형인지 구분
    # polymorphic_on과 polymorphic_identity를 사용한 싱글 테이블 상속(Single Table Inheritance) 구조
    # 이를 통해 IrisResult와 LoanResult 같은 특정 서비스의 예측 결과를 유연하게 확장,SQLAlchemy의 고급 기능
    type = db.Column(db.String(50))
    __mapper_args__ = {
        'polymorphic_on': type,
        'polymorphic_identity': 'prediction_result'
    }
    user = db.relationship("User", back_populates="prediction_results")
    api_key = db.relationship("APIKey", back_populates="prediction_results")
    service = db.relationship('Service', back_populates='prediction_results')
    def __repr__(self) -> str:
        return f"<PredictionResult(user_id={self.user_id}, service_id={self.service_id}, predicted_class='{self.predicted_class}')>"



