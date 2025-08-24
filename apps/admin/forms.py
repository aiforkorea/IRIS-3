# apps/admin/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from apps.dbmodels import User, UserType

# --- Form Classes ---
class EditUserForm(FlaskForm):
    """사용자 정보 수정을 위한 폼"""
    username = StringField('사용자 이름', validators=[DataRequired(message="사용자 이름을 입력해주세요.")])
    email = StringField('이메일', validators=[DataRequired(message="이메일을 입력해주세요."), Email(message="유효한 이메일 주소를 입력해주세요.")])
    submit = SubmitField('수정 완료')

    def __init__(self, original_user, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_user = original_user

    def validate_email(self, field):
        if field.data != self.original_user.email:
            if User.query.filter_by(email=field.data).first():
                raise ValidationError('이미 사용 중인 이메일입니다.')

class CreateUserForm(FlaskForm):
    """신규 사용자 생성을 위한 폼"""
    username = StringField('사용자 이름', validators=[DataRequired(message="사용자 이름을 입력해주세요.")])
    email = StringField('이메일', validators=[DataRequired(message="이메일을 입력해주세요."), Email(message="유효한 이메일 주소를 입력해주세요.")])
    password = PasswordField('비밀번호', validators=[DataRequired(message="비밀번호를 입력해주세요.")])
    # EqualTo 검사기를 confirm_password 필드에 추가하는 것이 더 일반적입니다.
    # 이렇게 하면 password 필드의 유효성 검사기와 분리되어 오류 메시지가 더 명확해집니다.
    confirm_password = PasswordField('비밀번호 확인', validators=[DataRequired(message="비밀번호를 다시 입력해주세요."), EqualTo('password', message='비밀번호가 일치하지 않습니다.')])
    user_type = SelectField('사용자 역할', choices=[(t.value, t.name.title()) for t in UserType], validators=[DataRequired()])
    is_active = BooleanField('계정 활성화', default=True)
    submit = SubmitField('사용자 생성')

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('이미 존재하는 사용자 이름입니다.')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('이미 존재하는 이메일입니다.')
        

        