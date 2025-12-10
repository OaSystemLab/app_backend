from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import ApprovalRequest, ApprovalStatus, CancelCooldown
from django.utils import timezone # 처리 시각 저장을 위해 필요
from datetime import timedelta
# -----------------------------------------------------
# Custom Admin Actions (일괄 승인/거부)
# -----------------------------------------------------

@admin.action(description=_('선택된 요청을 승인으로 변경'))
def approve_requests(modeladmin, request, queryset):
    """선택된 요청들을 'APPROVED' 상태로 변경하고 처리 시각을 기록합니다."""
    # 이미 처리된 요청(APPROVED, REJECTED, CANCELED)을 제외하고 PENDING인 요청만 처리
    pending_requests = queryset.filter(status=ApprovalStatus.PENDING)

    # 업데이트
    updated_count = pending_requests.update(
        status=ApprovalStatus.APPROVED,
        approved_or_rejected_at=timezone.now()
    )

    modeladmin.message_user(
        request,
        _('%d개의 요청이 성공적으로 승인되었습니다.' % updated_count)
    )

@admin.action(description=_('선택된 요청을 거부로 변경'))
def reject_requests(modeladmin, request, queryset):
    """선택된 요청들을 'REJECTED' 상태로 변경하고 처리 시각을 기록합니다."""
    pending_requests = queryset.filter(status=ApprovalStatus.PENDING)

    updated_count = pending_requests.update(
        status=ApprovalStatus.REJECTED,
        approved_or_rejected_at=timezone.now(),
        reason=_('관리자에 의한 일괄 거부') # 일괄 거부 사유 기본값 설정
    )

    modeladmin.message_user(
        request,
        _('%d개의 요청이 성공적으로 거부되었습니다.' % updated_count)
    )


# -----------------------------------------------------
# ModelAdmin Customization
# -----------------------------------------------------

class ApprovalRequestAdmin(admin.ModelAdmin):
    # 목록 페이지에 표시할 필드
    list_display = (
        'id',
        'requestee_nickname',
        'approver_nickname',
        'request_type',
        'status',
        'requested_at',
        'approved_or_rejected_at'
    )

    # 목록 페이지에서 클릭하여 상세 페이지로 이동할 수 있는 필드
    list_display_links = ('id', 'request_type')

    # 필터링 옵션
    list_filter = (
        'status',
        'request_type',
        'requested_at'
    )

    # 검색 기능
    search_fields = (
        'requestee__nick_name',
        'requestee__email',
        'approver__nick_name',
        'approver__email',
        'details' # JSON 필드도 검색 가능
    )

    # 목록 페이지에서 바로 수정 가능한 필드 (Status는 변경 로직이 복잡하므로 제외)
    # list_editable = ('status',)

    # 상세 페이지에서 필드 그룹화
    fieldsets = (
        (_('요청 정보'), {
            'fields': ('requestee', 'approver', 'request_type', 'details')
        }),
        (_('처리 상태'), {
            'fields': ('status', 'reason', 'approved_or_rejected_at')
        }),
        (_('타임스탬프'), {
            'fields': ('requested_at',),
            'classes': ('collapse',), # 필드셋을 접을 수 있도록 설정
        }),
    )

    # 상세 페이지에서 읽기 전용 필드 설정 (수정 방지)
    readonly_fields = ('requestee', 'approver', 'requested_at', 'approved_or_rejected_at')

    # 팝업 드롭다운 대신 원본 입력 폼을 사용하여 FK 필드 최적화 (FK가 많은 경우 유용)
    raw_id_fields = ('requestee', 'approver')

    # 커스텀 액션 등록
    actions = [approve_requests, reject_requests]

    # ForeignKey 필드의 사용자 이름/닉네임을 목록에 표시하기 위한 메서드
    @admin.display(description=_('요청자'))
    def requestee_nickname(self, obj):
        # requestee 객체에 nick_name 필드가 있다고 가정
        return obj.requestee.nick_name if hasattr(obj.requestee, 'nick_name') else obj.requestee.email

    @admin.display(description=_('승인자'))
    def approver_nickname(self, obj):
        # approver 객체에 nick_name 필드가 있다고 가정
        return obj.approver.nick_name if hasattr(obj.approver, 'nick_name') else obj.approver.email

    # 모델 등록
admin.site.register(ApprovalRequest, ApprovalRequestAdmin)


# -----------------------------------------------------
# CancelCooldownAdmin Customization (쿨다운 기록 관리)
# -----------------------------------------------------

@admin.register(CancelCooldown)
class CancelCooldownAdmin(admin.ModelAdmin):
    # 목록 페이지에 표시할 필드
    list_display = (
        'user_display',
        'request_type_display',
        'deleted_at',
        'remaining_cooldown_time'
    )

    # 필터링 옵션
    list_filter = (
        'request_type',
        'deleted_at'
    )

    # 검색 기능 (쿨다운이 적용된 사용자를 쉽게 찾기 위함)
    search_fields = (
        'user__email',
        'user__nick_name',
        'request_type'
    )

    # 상세 페이지에서 수정 불가능한 필드
    readonly_fields = ('user', 'request_type', 'deleted_at')

    # 사용자 이름 표시
    @admin.display(description=_('사용자'))
    def user_display(self, obj):
        # user 객체에 nick_name 필드가 있다면 닉네임을, 없다면 이메일을 표시
        if hasattr(obj.user, 'nick_name') and obj.user.nick_name:
            return f"{obj.user.nick_name} ({obj.user.email})"
        return obj.user.email

    # 요청 유형의 Label 표시
    @admin.display(description=_('요청 유형'))
    def request_type_display(self, obj):
        return obj.get_request_type_display()

    # 남은 쿨다운 시간을 계산하여 표시 (Read-only)
    @admin.display(description=_('남은 쿨다운 시간'))
    def remaining_cooldown_time(self, obj):
        # utils/cooldown.py에서 정의한 쿨다운 시간 (5분)을 사용한다고 가정
        COOLDOWN_MINUTES = 5
        cooldown_duration = timedelta(minutes=COOLDOWN_MINUTES)

        time_since_delete = timezone.now() - obj.deleted_at

        if time_since_delete < cooldown_duration:
            remaining_time = (cooldown_duration - time_since_delete).total_seconds()

            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)

            # 남은 시간이 있는 경우 HTML로 색상을 입혀 강조 (선택 사항)
            return f'{minutes}분 {seconds}초'
        else:
            # 쿨다운 시간이 지났으나 기록이 남아있는 경우
            return '만료됨 (삭제 필요)'

    # 만료된 기록은 자동으로 삭제할 수 있도록 액션 추가 (선택 사항)
    actions = ['delete_expired_records']

    @admin.action(description=_('만료된 쿨다운 기록 삭제'))
    def delete_expired_records(modeladmin, request, queryset):
        COOLDOWN_MINUTES = 5
        cutoff_time = timezone.now() - timedelta(minutes=COOLDOWN_MINUTES)

        # 쿨다운 시간을 초과한 기록만 필터링하여 삭제
        expired_records = queryset.filter(deleted_at__lt=cutoff_time)
        deleted_count, _ = expired_records.delete()

        modeladmin.message_user(
            request,
            _('%d개의 만료된 쿨다운 기록이 삭제되었습니다.' % deleted_count)
        )