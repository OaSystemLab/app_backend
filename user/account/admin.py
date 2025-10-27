from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserInfo, UserEmail # UserInfo, UserEmail 모델 임포트

# 1. UserEmail 모델을 UserInfo 관리자 페이지에 인라인으로 표시하기 위한 클래스
class UserEmailInline(admin.StackedInline):
    """
    UserInfo 편집 페이지에 UserEmail 모델을 인라인으로 표시
    """
    model = UserEmail
    # UserInfo와 UserEmail은 1:1 관계이므로 can_delete=False 설정하여 항상 존재하도록 보장
    can_delete = False
    verbose_name_plural = '이메일 인증 정보'
    # 표시할 필드 지정 (id 필드는 기본적으로 표시되므로 제외)
    fields = (
        'email_auth',
        'email_auth_count',
        'email_auth_date',
        'email_auth_code',
        'email_refresh_count',
        'email_auth_lock',
        'email_lock_time',
        'email_reauth_count',
        'email_reauth_lock',
        'email_reauth_date',
    )
    # 관리자가 임의로 변경하지 못하도록 읽기 전용 필드 지정
    readonly_fields = (
        'email_auth_date',
        'email_lock_time',
        'email_reauth_date'
    )


# 2. UserInfo 모델을 위한 커스텀 관리자 클래스
@admin.register(UserInfo)
class UserInfoAdmin(BaseUserAdmin):
    # 조건부 인라인 표시를 위해 get_inlines 메서드 사용
    # inlines = (UserEmailInline,)

    # 사용자 목록 페이지에 표시할 필드 목록
    list_display = ('email', 'nick_name', 'family_level', 'is_staff', 'is_active')

    list_filter = ('is_staff', 'is_superuser', 'is_active')

    # 커스텀 필드를 위한 검색 필드 재정의
    search_fields = ('email', 'nick_name', 'oas_group_id')
    ordering = ('email',)

    # Fieldsets: 사용자 편집 페이지에 표시할 필드를 그룹별로 정의합니다.
    fieldsets = (
        (None, {'fields': ('email', 'password', 'nick_name')}), # 필수 로그인 정보
        ('가족 인증', {'fields': ('family_group_id', 'family_level', 'family_auth_count')}),
        ('제어기 인증', {'fields': ('oas_group_id',)}),
        ('중요 날짜', {'fields': ('last_login', 'date_joined')}),
        ('권한', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}), # groups, user_permissions 추가
    )

    # add_fieldsets: 사용자 추가 페이지에 표시할 필드를 정의합니다.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'nick_name'), # password2는 비밀번호 확인을 위해 필요합니다.
        }),
    )

    # 요청하신 로직: UserInfo 인스턴스가 생성(저장)될 때만 UserEmail 인라인을 표시합니다.
    def get_inlines(self, request, obj=None):
        """
        사용자 추가 페이지(obj is None)에서는 UserEmail 인라인을 숨깁니다.
        """
        if obj is None:
            return [] # 사용자 추가 페이지일 때는 인라인을 반환하지 않음
        return [UserEmailInline] # 사용자 편집 페이지일 때는 인라인을 반환
