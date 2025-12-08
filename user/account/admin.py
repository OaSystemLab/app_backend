from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserInfo, UserEmail, EmailLog, UserGroup

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
        'email_code_date',
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

@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    """
    UserGroup 모델의 관리자 페이지 설정입니다.
    """

    # 1. 목록에 표시할 필드 (List Display)
    # 관리자 목록 페이지에서 가장 중요한 정보를 한눈에 볼 수 있도록 설정합니다.
    list_display = (
        'family_group_id',
        'user',
        'get_nick_name',    # 사용자 Nick Name
        'get_family_level',
        # 'master_id',
        'create_date'
    )

    # 2. 검색 필드 (Search Fields)
    # 목록 상단에 검색창을 만들어 해당 필드로 검색할 수 있도록 합니다.
    search_fields = (
        'family_group_id',  # 그룹 ID로 검색
        'user',             # 사용자 email
        'get_nick_name',    # 사용자 Nick Name
        'get_family_level',        # 닉네임으로 검색
        # 'master_id',        # 마스터 ID로 검색
    )

    # # 3. 필터링 필드 (List Filter)
    # # 목록 오른쪽에 필터 사이드바를 만들어 필터링 할 수 있도록 합니다.
    # list_filter = (
    #     'family_level', # 마스터/일반 사용자로 필터링
    #     'create_date',  # 생성 일자로 필터링
    # )

    # 4. 읽기 전용 필드 (Readonly Fields)
    # 사용자가 생성 일자를 변경하지 못하도록 읽기 전용으로 설정합니다.
    readonly_fields = (
        'create_date',
        'get_nick_name',      # 👈 fieldsets에서 사용하려면 반드시 필요
        'get_family_level',
    )

    # 1. 닉네임(nick_name)을 가져오는 메서드
    def get_nick_name(self, obj):
        """UserGroup에 연결된 UserInfo 객체의 nick_name을 반환합니다."""
        # obj는 현재 UserGroup 인스턴스입니다.
        # obj.user를 통해 연결된 UserInfo 객체에 접근하고 nick_name 필드를 가져옵니다.
        if obj.user:
            return obj.user.nick_name
        return "N/A"
    # 관리자 페이지 목록에 표시될 컬럼 헤더 이름 설정
    get_nick_name.short_description = '닉네임'
    get_nick_name.admin_order_field = 'user__nick_name' # 닉네임으로 정렬 가능하도록 설정 (UserInfo 모델에 nick_name 필드가 있을 경우)
    # 2. 가족 레벨(family_level)을 가져오는 메서드
    def get_family_level(self, obj):
        """UserGroup에 연결된 UserInfo 객체의 family_level을 반환합니다."""
        if obj.user:
            # 👈 UserInfo 객체를 통해 family_level에 접근합니다.
            return obj.user.family_level
        return "N/A"

    get_family_level.short_description = '가족 레벨'
    get_family_level.admin_order_field = 'family_level' # 이 필드는 UserGroup에 있으므로 바로 정렬 가능

    # 5. 레코드 상세 화면의 필드 순서 및 그룹화 (Fieldsets)
    # 상세 보기/수정 페이지에서 필드를 그룹별로 정리하여 보여줍니다.
    fieldsets = (
        ('그룹 정보', {
            'fields': ('family_group_id',),
        }),
        ('사용자 정보', {
            'fields': ('user', 'get_nick_name', 'get_family_level'),
        }),
        ('시간', {
            'fields': ('create_date',),
        }),
    )

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    # Admin 페이지에 표시할 필드
    list_display = (
        'email',
        'log_type',
        'created_at',
        'task_id',
        'error_message_summary' # 짧은 오류 메시지 요약 함수 사용
    )
    # 필터링 옵션
    list_filter = (
        'log_type',
        'created_at'
    )
    # 검색 필드
    search_fields = (
        'email',
        'error_message'
    )
    # 수정할 수 없는 필드 설정 (읽기 전용)
    readonly_fields = (
        'email',
        'task_id',
        'log_type',
        'error_message',
        'created_at'
    )

    # 긴 오류 메시지를 Admin 목록에서 짧게 보여주기 위한 함수
    def error_message_summary(self, obj):
        return obj.error_message[:100] + '...' if obj.error_message and len(obj.error_message) > 100 else obj.error_message
    error_message_summary.short_description = '오류 요약'