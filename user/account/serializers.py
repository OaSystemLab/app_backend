# serializers.py 파일은 **Django REST Framework (DRF)**에서 사용하는 핵심 구성 요소로,
# 주로 데이터 변환 및 유효성 검사의 역할을 담당합니다.

# UserRegistrationSerializer는 사용자 등록을 위한 역직렬화 및 생성에 초점을 맞추고 있습니다.

# 입력 데이터 정의:
# API 요청에서 email, nick_name, password, password2 네 가지 필드만 받도록 정의합니다.
# (모델에 있는 다른 필드들은 자동으로 처리되거나 기본값으로 설정됨)

# 유효성 검사 (Validation):
# 필수 유효성: password와 password2가 서로 일치하는지 확인합니다.
# 모델 유효성: email이나 nick_name이 이미 DB에 존재하는지 등 모델 수준의 제약 조건을 검사합니다.

# 모델 생성 (.create()):
# 유효성 검사를 통과한 데이터를 바탕으로 UserInfo 객체를 실제로 생성합니다.
# 이때 password 필드는 반드시 해시(암호화) 처리하여 안전하게 저장하도록 처리합니다.

# 요약하자면, serializers.py는 **클라이언트(브라우저/앱)**와 Django 서버 사이에서 오가는 데이터를 검증하고,
# 파이썬 객체와 웹 통신 형식(JSON) 사이를 번역해주는 통로 관리자 역할을 합니다.


from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from django.utils.translation import gettext_lazy as _
from .models import UserInfo , OasGroup, UserEmail
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import ValidationError as DRFValidationError

# ----------------------------------------------------------------------
# 1. 사용자 등록 View
# ----------------------------------------------------------------------
class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    UserInfo 모델 기반의 사용자 등록 Serializer.
    입력 필드: email, password, password2, nick_name
    """
    # password1과 password2를 write_only 필드로 추가 (응답에 포함되지 않음)
    password1 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        label=_("비밀번호")
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        label=_("비밀번호 확인")
    )

    class Meta:
        model = UserInfo
        # 클라이언트로부터 입력받을 필드 목록
        fields = ('email', 'nick_name', 'password1', 'password2')
        # 읽기 전용 필드 (선택 사항이지만 명확히 하기 위해 추가)
        read_only_fields = ('is_active', 'is_staff', 'is_superuser')

    def validate(self, data):
        """
        password1와 password2의 일치 여부를 확인하고,
        Django의 기본 비밀번호 유효성 검사를 수행합니다.
        """
        if data['password1'] != data['password2']:
            raise serializers.ValidationError({"password2": _("비밀번호가 일치하지 않습니다.")})

        # password2는 모델에 저장할 필요가 없으므로 삭제합니다.
        data.pop('password2')

        # Django의 기본 비밀번호 유효성 검사 적용 (settings.AUTH_PASSWORD_VALIDATORS)
        try:
            # UserInfo 인스턴스가 아직 없으므로 None을 전달합니다.
            validate_password(data['password1'], user=None)
        except exceptions.ValidationError as e:
            # 유효성 검사 오류 발생 시 DRF 에러로 변환하여 응답
            raise serializers.ValidationError({"password1": list(e.messages)})

        return data

    def create(self, validated_data):
        """
        검증된 데이터를 사용하여 새로운 UserInfo 인스턴스를 생성하고 비밀번호를 해시합니다.
        family_level 등 나머지 필드는 models.py에 정의된 기본값이 사용됩니다 ('none', '0' 등).
        """
        user = UserInfo.objects.create_user(
            email=validated_data['email'],
            nick_name=validated_data['nick_name'],
            password=validated_data['password1']
            # create_user 메서드는 models.py의 UserInfoManager에 정의되어 있습니다.
            # 이외의 모든 필드(family_level, family_auth_count 등)는 기본값이 적용됩니다.
        )
        return user

# ----------------------------------------------------------------------
# 2. 사용자 로그인 View (추가)
# ----------------------------------------------------------------------
class UserLoginSerializer(serializers.Serializer):
    """
    사용자 로그인을 위한 Serializer.
    입력 필드: email, password
    로그인 시도는 view에서 처리하며, 이 Serializer는 데이터의 형식과 유효성만 검사합니다.
    """
    email = serializers.EmailField(
        max_length=255,
        label=_("이메일")
    )
    password = serializers.CharField(
        max_length=128,
        write_only=True,
        style={'input_type': 'password'},
        label=_("비밀번호")
    )

    def validate(self, data):
        """
        입력된 데이터의 기본적인 형식 유효성을 검사합니다.
        (실제 사용자 인증은 view나 별도의 인증 백엔드에서 수행하는 것이 일반적입니다.)
        """
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError(_("이메일과 비밀번호는 필수 입력 항목입니다."))

        # 추가적인 복잡한 인증(DB 조회, 암호 비교)은 view나 custom authenticate()에서 처리
        return data


# ----------------------------------------------------------------------
# 3. api/token 이용한 로그인시 전달 해 줄 정보
# ----------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # 부모 클래스의 get_token을 호출하여 Access 및 Refresh 토큰 객체를 생성합니다.
        token = super().get_token(user)

        # 토큰의 페이로드에 원하는 사용자 정보를 추가합니다.
        # 일반적으로 'user_id' 또는 'id'를 사용합니다.
        # 여기서는 UserInfo 모델의 id 값을 추가합니다.
        token['user_id'] = user.id  # user는 인증된 UserInfo 인스턴스입니다.
        token['nick_name'] = user.nick_name # 닉네임도 추가 가능

        # UserEmail 모델의 이메일 인증 상태를 추가합니다.
        # related_name='email_info'로 접근합니다.
        if hasattr(user, 'email_info'):
             token['email_auth'] = user.email_info.email_auth
        else:
             token['email_auth'] = False # UserEmail 레코드가 없는 경우를 대비

        return token

    def validate(self, attrs):
        try:
            # 부모 클래스의 validate 메서드를 호출하여 토큰 쌍을 얻습니다.
            # 이 과정에서 인증(authenticate)이 실패하면 AuthenticationFailed 예외가 발생합니다.
            data = super().validate(attrs)
        except AuthenticationFailed:
            # === 이 부분을 수정합니다! ===
            # 인증 실패 시 발생하는 AuthenticationFailed를 가로채고,
            # Custom Validation Error를 발생시켜 non_field_errors를 커스텀합니다.
            raise serializers.ValidationError({
                "detail": _("제공된 인증 정보가 유효하지 않습니다. 이메일 또는 비밀번호를 확인해 주세요.")
            }, code='authentication')

        # 사용자 ID를 응답 데이터에 직접 추가합니다.
        # self.user는 TokenObtainPairSerializer의 validate 과정에서 설정됩니다.
        data['user_id'] = self.user.id
        data['nick_name'] = self.user.nick_name

        # family_group_id도 추가
        #data['family_group_id'] = self.user.family_group_id

        # UserEmail 모델의 이메일 인증 상태를 응답에 포함합니다.
        if hasattr(self.user, 'email_info'):
             data['email_auth'] = self.user.email_info.email_auth
        else:
             data['email_auth'] = False

        return data

# ----------------------------------------------------------------------
# 4. 임시 2025.10.27 View (삭제 필요...)
# ----------------------------------------------------------------------
class OasGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = OasGroup
        # API 응답에 포함할 필드를 지정합니다.
        # 모든 필드를 포함하려면 '__all__'을 사용하거나, 필요한 필드만 리스트로 지정합니다.
        fields = [
            'oas_group_id',
            'oas_info_id',
            'oas_name',
            'created_at'
        ]
        # 또는 fields = '__all__'

# ----------------------------------------------------------------------
# 5. email 인증 코드 요청 하기 전에 검증 하는 부분
# ----------------------------------------------------------------------
class EmailAuthSendSerializer(serializers.Serializer):
    """
    로그인된 사용자의 정보를 사용하여 이메일 인증 코드를 전송하기 위한 Serializer입니다.
    """

    def validate(self, data):
        # View에서 self.request.user를 context로 넘겨받는다고 가정합니다.
        user = self.context['request'].user

        # 1. 사용자 객체 인증 여부 확인 (수정된 부분)
        if not user.is_authenticated:
            # DRFValidationError를 사용하여 detail 메시지 반환
            raise DRFValidationError(
                {"detail": _("요청을 처리하려면 유효한 로그인 토큰이 필요합니다.")},
                code='not_authenticated'
            )

        # 2. UserEmail 객체 조회 (수정된 부분)
        try:
            email_info = user.email_info
        except UserEmail.DoesNotExist:
            raise DRFValidationError(
                {"detail": _("계정에 연결된 인증 정보가 누락되었습니다. 관리자에게 문의해 주세요.")},
                code='info_missing'
            )

        # 3. 이미 인증이 완료되었는지 확인
        # if email_info.email_auth:
        #     raise DRFValidationError(
        #         {"detail": _("이미 이메일 인증이 완료된 계정입니다.")},
        #         code='already_verified'
        #     )

        # 4. 인증 잠금 상태 확인 (로직은 그대로 유지)
        # TODO. 로직 처리 할때 ..
        # if email_info.email_auth_lock:
        #     raise serializers.ValidationError(_("인증 시도 횟수 초과로 계정이 일시적으로 잠겼습니다. 나중에 다시 시도해 주세요."))

        # 유효성 검사를 통과한 UserEmail 객체를 context에 저장하여 view에서 사용
        self.context['email_info'] = email_info

        return data # 이제 data는 빈 딕셔너리가 될 수 있습니다.
# ----------------------------------------------------------------------
# 6. 인증 메일서 받은 코드 검증 하기 전에 체크 하는 부분
# ----------------------------------------------------------------------
class EmailAuthConfirmSerializer(serializers.Serializer):
    """
    사용자로부터 받은 이메일과 인증 코드를 검증하고,
    인증이 완료되면 UserEmail 모델의 상태를 업데이트할 준비를 합니다.
    """
    # email = serializers.EmailField(
    #     max_length=100,
    #     required=True,
    #     label=_("이메일")
    # )
    auth_code = serializers.CharField(
        max_length=10, # UserEmail 모델의 max_length에 맞춰 10으로 설정
        required=True,
        label=_("인증 코드")
    )

    def validate(self, data):
        # View에서 self.request.user를 context로 넘겨받는다고 가정합니다.
        user = self.context['request'].user
        auth_code = data.get('auth_code')

        # 1. 사용자 객체 인증 여부 확인 (View의 Permission 설정으로 걸러지지만 안전을 위해 유지)
        if not user.is_authenticated:
            # DRFValidationError를 사용하여 detail 메시지 반환
            raise DRFValidationError(
                {"detail": _("로그인이 필요합니다.")},
                code='not_authenticated'
            )
        # 2. UserEmail 객체 확인
        try:
            email_info = user.email_info
        except UserEmail.DoesNotExist:
            raise DRFValidationError(
                {"detail": _("사용자 이메일 인증 정보가 누락되었습니다.")},
                code='info_missing'
            )
        # 3. 이미 인증이 완료되었는지 확인
        # if email_info.email_auth:
        #     raise DRFValidationError(
        #         {"detail": _("이미 이메일 인증이 완료된 계정입니다.")},
        #         code='already_verified'
        #     )
        # 4. 인증 코드 일치 여부 확인 (수정된 부분)
        if not email_info.email_auth_code or email_info.email_auth_code != auth_code:
            # === 이 부분을 DRFValidationError를 사용하여 detail 응답으로 변경 ===
            raise DRFValidationError(
                {"detail": _("인증 코드가 일치하지 않습니다. 다시 확인해 주세요.")},
                code='code_mismatch'
            )

        # TODO: 여기에 코드 유효 기간 확인 로직을 추가할 수 있습니다.

        # 유효성 검사를 통과한 UserEmail 객체를 context에 저장하여 view에서 사용
        self.context['email_info'] = email_info

        return data