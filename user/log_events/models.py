# log_events/models.py

from django.db import models
from django.conf import settings # User 모델 참조를 위해 settings 임포트

# ----------------------------------------------------------------------
# 1. Project Log Entry Model (통합 이벤트 기록)
# ----------------------------------------------------------------------
class ProjectLogEntry(models.Model):
    """
    프로젝트 내 모든 앱에서 발생한 중요한 이벤트나 예외를 기록합니다.
    """
    # 이벤트 발생 앱 (어디서 발생했는지 구분)
    app_name = models.CharField(
        max_length=50,
        verbose_name='발생 앱'
    )
    # 이벤트 발생 시간
    logged_at = models.DateTimeField(
        verbose_name='기록 시간',
        auto_now_add=True
    )
    # 이벤트 발생 사용자 (로그인하지 않은 경우 NULL 허용)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='관련 사용자'
    )
    # 이벤트 레벨 (WARNING, ERROR 등)
    level = models.CharField(
        max_length=10,
        verbose_name='심각도'
    )
    # 발생한 예외 클래스 이름 또는 이벤트 타입
    event_type = models.CharField(
        max_length=100,
        verbose_name='이벤트 타입'
    )
    # 기록할 상세 내용
    message = models.TextField(
        verbose_name='상세 메시지'
    )
    # 요청 시 전달된 데이터 (분석을 위해 JSON 문자열로 저장)
    request_data = models.TextField(
        verbose_name='요청 데이터',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = '통합 이벤트 기록'
        verbose_name_plural = '통합 이벤트 기록'
        ordering = ['-logged_at']
        db_table = 'project_log_entry'

    def __str__(self):
        return f'[{self.app_name} | {self.level}] {self.event_type}'