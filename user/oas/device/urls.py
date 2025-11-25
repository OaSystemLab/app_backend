# oas/auth/device/urls.py

from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import OasGroupViewSet, OasInfoViewSet, AuthAPIView

# DefaultRouter 인스턴스를 생성합니다.
router = DefaultRouter()

# ViewSet을 라우터에 등록합니다.
# url prefix: 'groups' -> /groups/ 로 접근
router.register(r'groups', OasGroupViewSet, basename='oas-group')

# url prefix: 'infos' -> /infos/ 로 접근
router.register(r'infos', OasInfoViewSet, basename='oas-info')

urlpatterns = [
    # 라우터가 자동으로 생성한 URL들을 포함시킵니다.
    path('', include(router.urls)),

    # ⭐️ /oas/v1/device/auth/ 경로에 AuthAPIView 연결
    path('auth/', AuthAPIView.as_view(), name='device-auth'),
]