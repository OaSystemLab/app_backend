# log_events/admin.py

from django.contrib import admin
from .models import ProjectLogEntry

@admin.register(ProjectLogEntry)
class ProjectLogEntryAdmin(admin.ModelAdmin):
    """통합 이벤트 기록 관리자 설정"""

    list_display = (
        'logged_at',
        'app_name',
        'level',
        'event_type',
        'user'
    )

    list_display_links = ('logged_at', 'event_type')

    # 여러 앱의 로그를 쉽게 필터링할 수 있도록 'app_name' 필터 추가
    list_filter = (
        'app_name',
        'level',
        'event_type',
        'logged_at',
    )

    search_fields = (
        'message',
        'user__username',
        'event_type',
        'app_name'
    )

    # 읽기 전용 설정
    readonly_fields = [f.name for f in ProjectLogEntry._meta.get_fields()]

    # 추가, 수정 버튼을 숨기고 오직 조회만 가능하게 합니다.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False