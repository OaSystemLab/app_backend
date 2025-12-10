from django.db import models
from django.conf import settings # 커스텀 User 모델을 참조하기 위해 필요

# 요청 유형을 위한 상수 정의
# 이 유형은 요청이 어떤 종류의 작업인지 나타냅니다 (예: 이메일 변경, 그룹 가입 등).
class RequestType(models.TextChoices):
    EMAIL_CHANGE = 'email_change', '이메일 변경 요청'
    GROUP_JOIN = 'group_join', '그룹 가입 요청'
    DATA_ACCESS = 'data_access', '특정 데이터 접근 요청'
    # 필요한 다른 요청 유형 추가

# 요청 상태를 위한 상수 정의
class ApprovalStatus(models.TextChoices):
    PENDING = 'pending', '대기 중'
    APPROVED = 'approved', '승인됨'
    REJECTED = 'rejected', '거부됨'
    CANCELED = 'canceled', '취소됨'

class ApprovalRequest(models.Model):
    # 1. 요청자: 승인이 필요한 작업을 원하는 일반 사용자 ('user')
    # settings.AUTH_USER_MODEL을 사용하여 UserInfo 모델을 참조합니다.
    requestee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_requests',
        verbose_name='요청자 (일반 사용자)'
    )

    # 2. 승인자: 요청을 처리할 마스터 권한을 가진 사용자 ('master')
    # 실제 비즈니스 로직에서 family_level='master'인 사용자만 지정해야 합니다.
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_requests',
        verbose_name='승인자 (마스터 권한)'
    )

    # 3. 요청 유형: 이 요청이 어떤 종류의 작업인지 명시합니다.
    request_type = models.CharField(
        max_length=50,
        choices=RequestType.choices,
        verbose_name='요청 유형'
    )

    # 4. 요청 세부 정보: 요청과 관련된 추가 데이터 (JSON 형태로 저장)
    # 예: request_type이 'email_change'인 경우 {'new_email': 'new@example.com'}
    # 요청의 성격에 따라 필요한 정보를 유연하게 저장할 수 있습니다.
    details = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        verbose_name='요청 상세 정보 (JSON)'
    )

    # 5. 상태: 요청의 현재 처리 상태
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        verbose_name='상태'
    )

    # 6. 타임스탬프: 요청 및 처리 시간을 기록
    requested_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='요청 시각'
    )

    approved_or_rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='처리 시각'
    )

    # 7. 처리 사유: 승인자(마스터)가 거부했을 때 사유를 남길 수 있습니다.
    reason = models.TextField(
        blank=True,
        verbose_name='처리 사유'
    )

    class Meta:
        verbose_name = '승인 요청'
        verbose_name_plural = '승인 요청'
        ordering = ['-requested_at']

    def __str__(self):
        return f'[{self.get_status_display()}] {self.get_request_type_display()} by {self.requestee.nick_name}'

class CancelCooldown(models.Model):
    """
    ApprovalRequest가 삭제(취소)된 후 쿨다운 기간을 적용하기 위해
    최소한의 정보를 기록하는 모델.
    """
    # 요청자: 쿨다운을 적용할 사용자
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cooldown_records',
        verbose_name='쿨다운 사용자'
    )

    # 요청 유형: 어떤 유형의 요청에 쿨다운이 적용되는지
    request_type = models.CharField(
        max_length=50,
        choices=RequestType.choices, # 기존 RequestType 상수 재사용
        verbose_name='요청 유형'
    )

    # 마지막 삭제 시각: 쿨다운을 계산할 기준 시간
    deleted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='마지막 삭제 시각'
    )

    class Meta:
        verbose_name = '취소 쿨다운 기록'
        # 핵심: 사용자별, 요청 유형별로 하나의 활성 쿨다운 기록만 존재해야 함
        unique_together = ('user', 'request_type')
        ordering = ['-deleted_at']

    def __str__(self):
        return f'{self.user.get_username()} - {self.get_request_type_display()} 쿨다운'