from django.urls import path
from .views import UserRegistrationView,\
                   UserLoginView, \
                   EmailAuthSendView, \
                   EmailAuthConfirmView, \
                   EmailChangeRequestView, \
                   EmailChangeVerifyView, \
                   UserInfoListAPIView, \
                   UserInfoNickNameUpdateAPIView, \
                   MasterTransferView, \
                   FamilyGroupLeaveView, \
                   FamilyGroupKickView


urlpatterns = [
    # 사용자 등록 (회원가입) API
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    # 사용자 로그인 API (추가) --
    # 현재론 api/token 로그인 방식으로 인한 사용 중지
    # path('login/', UserLoginView.as_view(), name='user-login'),

    # 3. 이메일 인증 코드 전송
    # POST /api/v1/accounts/email/send/
    path('email/send/', EmailAuthSendView.as_view(), name='email-auth-send'),
    # 4. 이메일 인증 코드 확인 및 완료
    # POST /api/v1/accounts/email/confirm/
    path('email/confirm/', EmailAuthConfirmView.as_view(), name='email-auth-confirm'),

    path('email/change/request/', EmailChangeRequestView.as_view(), name='email_change_request'),
    path('email/change/verify/', EmailChangeVerifyView.as_view(), name='email_change_verify'),

    # UserGroup list 가져 오기
    path('group_list/', UserInfoListAPIView.as_view(), name='user-group-list'),
    path('nick_edit/', UserInfoNickNameUpdateAPIView.as_view(), name='user-nickname-edit'),
    # 마스터 권한 넘겨 주기
    path('group/transfer-master/', MasterTransferView.as_view(), name='transfer-master'),
    # 가족 그룹 탈퇴
    path('group/leave/', FamilyGroupLeaveView.as_view(), name='group-leave'),
    # API 요청: POST /api/group/kick/
    path('group/kick/', FamilyGroupKickView.as_view(), name='group-kick'),
]
