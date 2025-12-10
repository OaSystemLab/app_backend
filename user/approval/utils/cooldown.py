# your_app/utils/cooldown.py

from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from ..models import CancelCooldown, RequestType # 경로에 맞게 수정 필요

class RequestCooldownManager:
    """
    승인 요청 및 취소 시 쿨다운 로직을 관리하는 유틸리티 클래스.
    """
    COOLDOWN_MINUTES = 5

    def __init__(self, user, request_type):
        """쿨다운을 적용할 사용자 인스턴스와 요청 유형을 초기화합니다."""
        self.user = user
        self.request_type = request_type
        self.cooldown_duration = timedelta(minutes=self.COOLDOWN_MINUTES)

    def _get_cooldown_record(self):
        """현재 사용자와 요청 유형에 해당하는 쿨다운 기록을 조회합니다."""
        try:
            return CancelCooldown.objects.get(
                user=self.user,
                request_type=self.request_type
            )
        except CancelCooldown.DoesNotExist:
            return None

    def check_and_enforce_cooldown(self):
        """
        쿨다운 기간이 남아있는지 확인하고, 남아있다면 ValidationError를 발생시킵니다.
        쿨다운이 만료되었다면 해당 기록을 삭제합니다.
        """
        cooldown_record = self._get_cooldown_record()

        if cooldown_record:
            time_since_delete = timezone.now() - cooldown_record.deleted_at

            if time_since_delete < self.cooldown_duration:
                # 쿨다운이 아직 유효함: 오류 발생
                remaining_time = (self.cooldown_duration - time_since_delete).total_seconds()

                minutes = int(remaining_time // 60)
                seconds = int(remaining_time % 60)

                error_message = (
                    f'요청/취소 반복 방지를 위해 {RequestType(self.request_type).label} 요청은 '
                    f'{minutes}분 {seconds}초 후에 다시 시도할 수 있습니다.'
                )
                raise ValidationError(
                    {'detail': error_message},
                    code='cooldown_active'
                )

            # 쿨다운 만료: 기록 삭제
            cooldown_record.delete()

    def set_cooldown(self):
        """
        쿨다운 기록을 생성하거나 업데이트하여 쿨다운 타이머를 재설정합니다.
        (DELETE 요청 처리 시 호출)
        """
        CancelCooldown.objects.update_or_create(
            user=self.user,
            request_type=self.request_type,
            defaults={'deleted_at': timezone.now()}
        )