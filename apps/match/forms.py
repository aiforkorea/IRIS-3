# apps/match/forms.py
from flask import request
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, StringField, SubmitField, SelectField, widgets, DateField, FileField, ValidationError
from wtforms.validators import DataRequired, Optional
from apps.dbmodels import User, UserType, MatchStatus, MatchLogType

class MultiCheckboxField(SelectMultipleField):
    """체크박스를 여러 개 선택할 수 있는 필드"""
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class NewMatchForm(FlaskForm):
    """신규 매칭 탭의 검색 및 할당 폼"""
    email = StringField("이메일")
    start_date = DateField("시작일", format='%Y-%m-%d', render_kw={"placeholder": "YYYY-MM-DD"})
    end_date = DateField("종료일", format='%Y-%m-%d', render_kw={"placeholder": "YYYY-MM-DD"})
    search_submit = SubmitField("검색")
    expert_id = SelectField("전문가 선택", coerce=int, validators=[DataRequired()])
    assign_submit = SubmitField("매칭 생성")

# 수정된 MatchSearchForm 클래스
class MatchSearchForm(FlaskForm):
    user_id = StringField("사용자 ID")
    expert_id = StringField("전문가 ID")
    status = SelectField(
        "상태",
        choices=[],
        validators=[Optional()]   # choices를 빈 리스트로 초기화 (동적으로 할당 예정) + 필수입력 막기 (MissingDataError 예방)
    )
    start_date = DateField("시작일", format='%Y-%m-%d', render_kw={"placeholder": "YYYY-MM-DD"})
    end_date = DateField("종료일", format='%Y-%m-%d', render_kw={"placeholder": "YYYY-MM-DD"})
    search_submit = SubmitField("검색")
    match_ids = MultiCheckboxField("매칭 선택", coerce=int, choices=[])
    batch_expert_id = SelectField("전문가 할당", coerce=int, choices=[])
    batch_assign_submit = SubmitField("일괄 할당")
    batch_cancel_submit = SubmitField("일괄 취소")

    def validate_batch_expert_id(self, field):
        if 'batch_assign_submit' in request.form:
            if field.data == 0:
                raise ValidationError("전문가를 반드시 선택해야 합니다.")

# 추후 삭제                  
class LogSearchForm(FlaskForm):
    """로그 검색을 위한 폼"""
    keyword = StringField('키워드', render_kw={"placeholder": "ID, 로그 내용, 사용자/전문가 이메일 등"})
    start_date = DateField("시작일", format='%Y-%m-%d')
    end_date = DateField("종료일", format='%Y-%m-%d')
    submit = SubmitField("검색")            

class AdminLogSearchForm(FlaskForm):
    """관리자 로그 검색을 위한 폼"""
    keyword = StringField('키워드', render_kw={"placeholder": "user ID, expert ID, 로그타이틀, 내용 등"})
    # coerce=str을 추가하여 빈 문자열을 허용
    log_title = SelectField("로그 제목", choices=[('', '모든 제목')] + [(type.value, type.value) for type in MatchLogType], coerce=str)
    start_date = DateField("시작일", format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField("종료일", format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField("검색")    

