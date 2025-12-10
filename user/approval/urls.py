# app/urls.py
from django.urls import path
from .views import ApprovalRequestAPIView, PendingApprovalCheckAPIView, ApprovalRequestUpdateAPIView

urlpatterns = [
    # POST , DELETE
    path('request/', ApprovalRequestAPIView.as_view(), name='create-approval-request'),

    # 승인 요청 상태 업데이트 (PATCH /api/v1/approvals/request/123/update/)
    path(
        'request/<int:request_id>/update/',
        ApprovalRequestUpdateAPIView.as_view(),
        name='update-approval-status'
    ),
    # 나에게 들어온 승인 요청 확인 (GET)
    # 예시: GET /api/v1/approvals/check-pending/
    path('check-pending/', PendingApprovalCheckAPIView.as_view(), name='check-pending-approvals'),


]