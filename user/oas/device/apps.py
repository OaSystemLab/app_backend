from django.apps import AppConfig


class DeviceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'oas.device'

    # ⭐️ 이 부분을 추가/수정하여 Admin 섹션 이름을 변경합니다.
    verbose_name = "환경제어기"

    # label은 보통 앱 디렉토리의 마지막 이름(device)을 사용하지만,
    # 명시적으로 설정된 경우도 있으니 참고용으로 유지합니다.
    label = 'device'