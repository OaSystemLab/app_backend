from django.apps import AppConfig

class AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'account'

    # 앱이 로드될 때 signals.py를 가져와 시그널을 등록합니다.
    def ready(self):
        import account.signals
