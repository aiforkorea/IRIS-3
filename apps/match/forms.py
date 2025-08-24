from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, DateField
from wtforms.validators import DataRequired, Optional
from apps.dbmodels import MatchStatus

class MatchSearchForm(FlaskForm):
    user_id = StringField('일반 사용자 ID')
    expert_id = StringField('전문가 ID')
    status = SelectField('매칭 상태', choices=[('', '전체')] + [(s.value, s.name) for s in MatchStatus])
    start_date = DateField('시작일', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('종료일', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('검색')

class MatchManageForm(FlaskForm):
    user_id = StringField('일반 사용자 ID', validators=[DataRequired()])
    expert_id = StringField('전문가 ID', validators=[DataRequired()])
    status = SelectField('매칭 상태', choices=[(s.value, s.name) for s in MatchStatus], validators=[DataRequired()])
    submit = SubmitField('저장')