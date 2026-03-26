from django.urls import path
from .views import api_latest_data
from .views import DeviceRefreshView, DeviceSearchView, DashBoardView

urlpatterns = [
    # 기존 실시간 새로고침 API (GET)
    path('dev/refresh/', DeviceRefreshView.as_view(), name='device_refresh'),

    # 신규 날짜 범위 및 컬럼 검색 API (POST)
    path('dev/search/', DeviceSearchView.as_view(), name='device_search'), # 2. 검색 엔드포인트 추가

    # dh/
    path('dashboard/', DashBoardView.as_view(), name='dash_board'),
]