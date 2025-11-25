# oas/auth/device/admin.py

from django.contrib import admin
from .models import OasGroup, OasInfo

# ----------------------------------------------------------------------
# 1. OasGroup 관리자 설정
# ----------------------------------------------------------------------
@admin.register(OasGroup)
class OasGroupAdmin(admin.ModelAdmin):
    """OasGroup 모델을 위한 관리자 설정"""

    # 목록 페이지에 표시할 필드
    list_display = (
        'id',
        'oas_group_id',
        'oas_info_id',
        'oas_name',
        'created_at'
    )

    # 검색을 허용할 필드 (검색창이 생성됨)
    search_fields = (
        'oas_group_id',
        'oas_info_id',
        'oas_name'
    )

    # 필터링을 허용할 필드 (사이드바에 필터가 생성됨)
    list_filter = (
        'created_at',
    )

    # 객체 상세 페이지에서 수정할 수 없는 필드 (ID는 변경 불가)
    readonly_fields = (
        'id',
        'created_at'
    )


# ----------------------------------------------------------------------
# 2. OasInfo 관리자 설정
# ----------------------------------------------------------------------
@admin.register(OasInfo)
class OasInfoAdmin(admin.ModelAdmin):
    """OasInfo 모델을 위한 관리자 설정"""

    # 목록 페이지에 표시할 필드
    list_display = (
        'id',
        'site',
        'dong',
        'ho',
        'deviceId',
        'auth',
        'lock'
    )

    # 검색을 허용할 필드 (검색창이 생성됨)
    search_fields = (
        'site',
        'dong',
        'ho',
        'deviceId'
    )

    # 필터링을 허용할 필드
    list_filter = (
        'auth',        # 인증 상태
        'lock',        # 잠금 상태
        'auth_date',
        'lock_date',
        'created_at'
    )

    # 객체 상세 페이지에서 필드를 그룹화하여 보기 쉽게 만듭니다.
    fieldsets = (
        ('환경제어기 정보', {
            'fields': ('site', 'dong', 'ho', 'oas_id', 'deviceId', 'room'),
        }),
        ('인증 및 잠금 상태', {
            'fields': ('auth', 'auth_count', 'auth_date', 'lock', 'lock_date'),
        }),
        ('메타 정보', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',), # 이 섹션을 접을 수 있도록 설정
        }),
    )

    # 객체 상세 페이지에서 수정할 수 없는 필드
    readonly_fields = (
        'id',
        'created_at'
    )