# 인증 및 계정 생성

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed

from ..models import UserInfo

# ----------------------------------------------------------------------
# 1. 사용자 등록 Serializer
# ----------------------------------------------------------------------
class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    UserInfo 모델 기반의 사용자 등록 Serializer.

    입력 필드: email, password, password2, nick_name
    """
    password1 = serializers.CharField(
        write_only=True, required=True, style={'input_type': 'password'}, label=_("비밀번호")
    )
    password2 = serializers.CharField(
        write_only=True, required=True, style={'input_type': 'password'}, label=_("비밀번호 확인")
    )

    class Meta:
        model = UserInfo
        fields = ('email', 'nick_name', 'password1', 'password2')
        read_only_fields = ('is_active', 'is_staff', 'is_superuser')

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError({"password2": _("비밀번호가 일치하지 않습니다.")})

        data.pop('password2')

        try:
            validate_password(data['password1'], user=None)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError({"password1": list(e.messages)})

        return data

    def create(self, validated_data):
        user = UserInfo.objects.create_user(
            email=validated_data['email'],
            nick_name=validated_data['nick_name'],
            password=validated_data['password1']
        )
        return user

# ----------------------------------------------------------------------
# 2. 사용자 로그인 Serializer
# ----------------------------------------------------------------------
class UserLoginSerializer(serializers.Serializer):
    """ 사용자 로그인을 위한 Serializer. """
    email = serializers.EmailField(max_length=255, label=_("이메일"))
    password = serializers.CharField(max_length=128, write_only=True, style={'input_type': 'password'}, label=_("비밀번호"))

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError({"detail": "이메일과 비밀번호는 필수 입력 항목입니다."})

        return data


# ----------------------------------------------------------------------
# 3. JWT 토큰 Serializer (Custom)
# ----------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['user_id'] = user.id
        token['nick_name'] = user.nick_name
        token['oas_auth'] = False

        if hasattr(user, 'email_info'):
             token['email_auth'] = user.email_info.email_auth
        else:
             token['email_auth'] = False

        return token

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            raise serializers.ValidationError({
                "detail": "제공된 인증 정보가 유효하지 않습니다. 이메일 또는 비밀번호를 확인해 주세요."
            })

        data['user_id'] = self.user.id
        data['nick_name'] = self.user.nick_name
        data['oas_auth'] = False

        if hasattr(self.user, 'email_info'):
             data['email_auth'] = self.user.email_info.email_auth
        else:
             data['email_auth'] = False

        return data