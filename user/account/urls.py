from django.urls import path
from .views import UserRegistrationView, UserLoginView, OasGroupListAPIView


urlpatterns = [
    # 사용자 등록 (회원가입) API
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    # 사용자 로그인 API (추가) --
    # 현재론 api/token 로그인 방식으로 인한 사용 중지
    # path('login/', UserLoginView.as_view(), name='user-login'),

    path('oasgroups/', OasGroupListAPIView.as_view(), name='oasgroup-list'),
]
