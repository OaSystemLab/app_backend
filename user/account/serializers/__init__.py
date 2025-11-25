# my_app/serializers/__init__.py

# auth_serializers.py 에서 필요한 클래스들을 가져옵니다.
from .auth_serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    CustomTokenObtainPairSerializer
)

# email_serializers.py 에서 필요한 클래스들을 가져옵니다.
from .email_serializers import (
    EmailAuthSendSerializer,
    EmailAuthConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailChangeVerifySerializer
)

# 외부에서 'from .serializers import X' 로 접근할 수 있도록 노출합니다.
__all__ = [
    'UserRegistrationSerializer',
    'UserLoginSerializer',
    'CustomTokenObtainPairSerializer',
    'EmailAuthSendSerializer',
    'EmailAuthConfirmSerializer',
    'EmailChangeRequestSerializer',
    'EmailChangeVerifySerializer',
]