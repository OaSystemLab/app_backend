"""
URL configuration for user project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from account.views import CustomTokenObtainPairView

urlpatterns = [
    # Django Admin Site URL
    path('admin/', admin.site.urls),

    # 'account' 앱의 URL을 /api/v1/account/ 경로에 연결합니다. (v1 버전 적용)
    # 이제 /api/v1/account/register/ 와 /api/v1/account/login/ 경로로 접근할 수 있습니다.
    path('api/v1/account/', include('account.urls')),

    # djangorestframework-simplejwt의 토큰 엔드포인트를 추가합니다.
    # JWT 토큰을 얻는 엔드포인트: Access 및 Refresh 토큰 발급
    #path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # 변경: 커스텀 뷰 사용
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    # Access 토큰을 갱신하는 엔드포인트
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ⭐️ 새로 추가된 oas.auth.device 앱의 URL을 연결
    path('oas/v1/device/', include('oas.device.urls')),
    # Approval 앱의 URL을 /api/v1/approvals/ 경로로 연결
    path('api/v1/approvals/', include('approval.urls')),

]
