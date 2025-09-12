# apps/iris/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FloatField, PasswordField, SelectField, DateField
from wtforms.validators import DataRequired, Optional
from apps.iris.dbmodels import LogStatusType # 새로 추가된 enum
from apps.dbmodels import UsageType

class IrisUserForm(FlaskForm):
    sepal_length = FloatField('sepal_length', validators=[DataRequired()])
    sepal_width = FloatField('sepal width', validators=[DataRequired()])
    petal_length = FloatField('petal_length', validators=[DataRequired()])
    petal_width = FloatField('petal width', validators=[DataRequired()])
    submit = SubmitField('예측')

class EmptyForm(FlaskForm):
    pass

class IrisLogSearchForm(FlaskForm):
    """붓꽃 예측 로그 검색을 위한 폼"""
    keyword = StringField('키워드', render_kw={"placeholder": "사용자ID, 서비스ID, 추론ID 등"})
    usage_type = SelectField(
        "타입",
        choices=[('', '타입')] + [(type.value, type.value) for type in UsageType],
        coerce=str,
        validators=[Optional()]
    )
    log_status = SelectField(
        "상태",
        choices=[('', '상태')] + [(type.value, type.value) for type in LogStatusType],
        coerce=str,
        validators=[Optional()]
    )
    start_date = DateField("시작일", format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField("종료일", format='%Y-%m-%d', validators=[Optional()])
    date_field = SelectField(
        "기준",
        choices=[('timestamp', '로그시각'), ('inference_timestamp', '추론시각')],
        default='timestamp'
    )
    submit = SubmitField("검색")
