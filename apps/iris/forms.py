# apps/iris/forms.py
from flask_wtf import FlaskForm # <-- FlaskForm을 정확히 임포트했는지 확인
from wtforms import StringField, SubmitField, FloatField, PasswordField # 필요한 필드 임포트
from wtforms.validators import DataRequired, Email, Optional

class IrisUserForm(FlaskForm):
    sepal_length = FloatField('sepal_length', validators=[DataRequired()])
    sepal_width = FloatField('sepal width', validators=[DataRequired()])
    petal_length = FloatField('petal_length', validators=[DataRequired()])
    petal_width = FloatField('petal width', validators=[DataRequired()])
#    api_key = PasswordField('api_key', validators=[DataRequired()])
    submit = SubmitField('예측')

class EmptyForm(FlaskForm):
    pass
