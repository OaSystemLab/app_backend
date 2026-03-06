# oas/auth/device/urls.py

from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import  AuthAPIView, OasListAPIView, OasInfoRoomUpdateAPIView, UserAppOasRequest

# DefaultRouter 인스턴스를 생성합니다.
router = DefaultRouter()

urlpatterns = [
    # 라우터가 자동으로 생성한 URL들을 포함시킵니다.
    path('', include(router.urls)),

    # ⭐️ /oas/v1/device/auth/ 경로에 AuthAPIView 연결
    path('auth/', AuthAPIView.as_view(), name='device-auth'),
    # 환경제어기 리스트 가져 오기
    path('oas_list/', OasListAPIView.as_view(), name='oas_list'),
    # 환경제어기 방이름 변경
    path('oas_info/update_room/', OasInfoRoomUpdateAPIView.as_view(), name='update_oas_room'),
    # 환경제어기 Sensing 정보 요청.
    path('requset/', UserAppOasRequest.as_view(), name='request'),

]