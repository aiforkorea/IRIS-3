# apps/iris/dbmodels.py
from apps.dbmodels import db, PredictionResult # PredictionResult를 임포트
# 이 예측 결과 기본 모델을 상속하여 각 서비스별 특수화 필드 추가
class IrisResult(PredictionResult):
    __tablename__ = 'iris_results'
    id = db.Column(db.Integer, db.ForeignKey('prediction_results.id'), primary_key=True)
    sepal_length = db.Column(db.Float, nullable=False)
    sepal_width = db.Column(db.Float, nullable=False)
    petal_length = db.Column(db.Float, nullable=False)
    petal_width = db.Column(db.Float, nullable=False)
    redundancy = db.Column(db.Boolean, default=False) # 레코드값이 같은 경우, 중복된 컬럼으로 표시
   
    __mapper_args__ = {
        'polymorphic_identity': 'iris'
    }

    def __repr__(self) -> str:
        return (f"<IrisResult(sepal_length={self.sepal_length}, sepal_width={self.sepal_width}, "
                f"petal_length={self.petal_length}, petal_width={self.petal_width}, predicted_class='{self.predicted_class}')>")
    
