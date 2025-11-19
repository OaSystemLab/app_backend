from django.urls import path
from .views import UserRegistrationView, UserLoginView, OasGroupListAPIView, EmailAuthSendView, EmailAuthConfirmView, EmailChangeRequestView, EmailChangeVerifyView


urlpatterns = [
    # 사용자 등록 (회원가입) API
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    # 사용자 로그인 API (추가) --
    # 현재론 api/token 로그인 방식으로 인한 사용 중지
    # path('login/', UserLoginView.as_view(), name='user-login'),

    # 4. 임시 2025.10.27 View (삭제 필요...)
    path('oasgroups/', OasGroupListAPIView.as_view(), name='oasgroup-list'),


    # 3. 이메일 인증 코드 전송
    # POST /api/v1/accounts/email/send/
    path('email/send/', EmailAuthSendView.as_view(), name='email-auth-send'),
    # 4. 이메일 인증 코드 확인 및 완료
    # POST /api/v1/accounts/email/confirm/
    path('email/confirm/', EmailAuthConfirmView.as_view(), name='email-auth-confirm'),

    path('email/change/request/', EmailChangeRequestView.as_view(), name='email_change_request'),
    path('email/change/verify/', EmailChangeVerifyView.as_view(), name='email_change_verify'),

]
