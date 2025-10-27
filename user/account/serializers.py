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
from .models import UserInfo , OasGroup# 이전에 정의한 커스텀 사용자 모델


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