# apps/iris/dbmodels.py
# apps/iris/dbmodels.py
from apps.dbmodels import db, PredictionResult, UsageType, func
import enum

# 로그 상태를 정의하는 Enum 추가
class LogStatusType(enum.Enum):
    PREDICTION = "추론"
    SUCCESS = "정상"
    DUPLICATE = "중복"
    CONFIRMED = "추론확인"
    MODIFIED = "추론수정"
    DELETED = "삭제"
    
    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_

# 기존 UsageLog 모델의 log_status를 enum으로 변경
# apps/dbmodels.py의 UsageLog 클래스도 같이 수정 필요
# dbmodels.py에 LogStatusType enum을 추가하는 것이 좋지만,
# 여기서는 iris 앱 내에서만 사용한다고 가정하고 별도 정의함.
# from apps.dbmodels import LogStatusType 추가 후,
# log_status = db.Column(db.Enum(LogStatusType), nullable=False) 로 수정해야 함.
# 여기서는 편의상 iris 앱 내에 정의하고 진행합니다.

class IrisResult(PredictionResult):
    __tablename__ = 'iris_results'
    id = db.Column(db.Integer, db.ForeignKey('prediction_results.id'), primary_key=True)
    sepal_length = db.Column(db.Float, nullable=False)
    sepal_width = db.Column(db.Float, nullable=False)
    petal_length = db.Column(db.Float, nullable=False)
    petal_width = db.Column(db.Float, nullable=False)
    redundancy = db.Column(db.Boolean, default=False)
    
    __mapper_args__ = {
        'polymorphic_identity': 'iris'
    }

    def __repr__(self) -> str:
        return (f"<IrisResult(sepal_length={self.sepal_length}, sepal_width={self.sepal_width}, "
                f"petal_length={self.petal_length}, petal_width={self.petal_width}, predicted_class='{self.predicted_class}')>")