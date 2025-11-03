# user/celery.py

import os
from celery import Celery

# 1. Django 설정 모듈을 Celery에 알려줍니다.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'user.settings')

# 2. Celery 앱 생성
# 'your_project_name'은 Celery 인스턴스의 이름으로 사용됩니다.
app = Celery('user')

# 3. Django 설정에서 Celery 설정을 로드합니다.
# 'CELERY_'로 시작하는 모든 설정 키를 사용합니다.
app.config_from_object('django.conf:settings', namespace='CELERY')

# 4. Celery가 자동적으로 앱 내의 모든 `tasks.py` 파일을 검색하도록 합니다.
# (task를 정의한 앱 이름 리스트를 명시적으로 설정하지 않아도 됨)
app.autodiscover_tasks()

# 5. 디버깅을 위한 기본 태스크 정의 (선택 사항)
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')