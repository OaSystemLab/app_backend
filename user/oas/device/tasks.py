import logging
from celery import shared_task
# AppMqttManager 임포트 (경로에 맞게 수정하세요)
from .utils.remote_manager import AppMqttManager

logger = logging.getLogger('celery_tasks')

@shared_task(bind=True, max_retries=3, default_retry_delay=5, name='oas.device.tasks.task_mqtt_broker_publish')
def task_mqtt_broker_publish(self, valid_data):
    try:
        manager = AppMqttManager()
        manager.broker_publish(valid_data)

    except ValueError as exc:
        # 잘못된 sitecode 등 로직 에러는 재시도 없이 종료
        #logger.error(f"영구적 실패 (재시도 중단): {exc}")
        print(f"영구적 실패 (재시도 중단): {exc}")
        return {"status": "failed", "reason": str(exc)}

    except Exception as exc:
        # 네트워크 오류, 500 에러 등은 재시도 진행
        #logger.warning(f"일시적 실패 (재시도 진행): {exc}")
        print(f"일시적 실패 (재시도 진행): {exc}")
        raise self.retry(exc=exc)