from django.utils import timezone

from ..models import OasGroup, OasInfo
from log_events.models import ProjectLogEntry # ⭐️ 통합 모델 임포트
from django.db import IntegrityError, DatabaseError
from typing import Optional


def OasInfoDelete(id : int):
    try:
        OasInfo.objects.filter(id=id).delete()
    except Exception as e:
        print(f"OasInfo 삭제 중 오류 발생: {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=None,
            level='ERROR',
            event_type='OasInfoDelete',
            message=f"OasInfo 삭제 중 오류 발생 {id}",
            request_data=f"{e}"
        )


def OasInfoSearchDeviceIdLock(device_id : str) -> bool:
    """
    주어진 device_id와 일치하는 OasInfo 레코드를 찾아 잠금(lock=True) 상태로 업데이트합니다.

    Args:
        device_id (str): 업데이트할 환경 제어기의 Device ID 값.
    Returns:
        update 성공 true, 실패 false
    """

    # 1. 현재 날짜를 가져옵니다. (OasInfo 모델의 lock_date가 DateField이므로 date 객체를 사용)
    current_date = timezone.now().date()

    try :
        # 2. filter()를 사용하여 쿼리셋을 선택하고, update()를 사용하여 일괄 업데이트를 수행합니다.
        # update()는 데이터베이스 레벨에서 바로 실행되므로 매우 빠릅니다.
        OasInfo.objects.filter(deviceId=device_id).update(
            lock=True,              # lock 필드를 True로 설정
            lock_date=current_date  # lock_date 필드를 현재 날짜로 설정
        )
        return True
    except Exception as e:
        print(f"OasInfo 객체 생성 중 알 수 없는 오류 발생: {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=None,
            level='ERROR',
            event_type='OasInfoSearchDeviceIdLock',
            message=f"OasInfo 객체 생성 중 알 수 없는 오류 발생 {device_id}",
            request_data=f"{e}"
        )
        return False

def OasInfoNewObject(initial_data: dict) -> Optional[int]:
    """
    Serializer의 initial_data를 사용하여 새로운 OasInfo 객체를 생성하고,
    성공하면 생성된 객체의 Primary Key(id)를, 실패하면 None을 반환합니다.

    Args:
        initial_data (dict): 클라이언트로부터 받은 원본 요청 데이터 (self.initial_data).

    Returns:
        Optional[int]: 객체 생성에 성공하면 생성된 객체의 id, 실패하면 None.
    """

    # 딕셔너리에서 필요한 필드 값을 추출합니다.
    # 주의: 'id' 필드는 OasInfo 모델에서 'oas_id'로 매핑될 가능성이 높습니다.
    # 여기서는 모델 필드명에 맞추어 데이터를 추출해야 합니다.
    try:
        # 1. OasInfo.objects.create()는 새로 생성된 인스턴스를 반환합니다.
        new_oas_info = OasInfo.objects.create(
            site=initial_data.get('site'),
            dong=initial_data.get('dong'),
            ho=initial_data.get('ho'),
            oas_id=initial_data.get('id'),
            deviceId=initial_data.get('deviceId'),
            room=None,
            auth=False,
            auth_count=0,
            auth_date=None,
            lock=False,
            lock_date=None
        )
        # 2. 성공적으로 객체가 생성되면, 해당 객체의 고유 ID를 반환합니다.
        # Django가 자동으로 생성한 Primary Key 필드 이름은 'id'입니다.
        return new_oas_info.id

    # 데이터베이스 제약 조건 위반 (예: deviceId unique_together 위반 등)
    except (IntegrityError, DatabaseError) as e:
        print(f"OasInfo 객체 생성 중 데이터베이스 오류 발생: {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=None,
            level='ERROR',
            event_type='OasInfoNewObject',
            message=f"OasInfo 객체 생성 중 데이터베이스 오류 발생",
            request_data=f"{e}"
        )
        # 오류 발생 시 False 반환
        return None
    # 기타 예외 (예: 필드 누락 등)
    except Exception as e:
        print(f"OasInfo 객체 생성 중 알 수 없는 오류 발생: {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=None,
            level='ERROR',
            event_type='OasInfoNewObject',
            message=f"OasInfo 객체 생성 중 오류 발생",
            request_data=f"{e}"
        )
        return None


def OasGroupCreateObject(group_id : str, info_id : str) -> Optional[int]:
    """
    OasGroup 객체를 생성하고,
    성공하면 생성된 객체의 Primary Key(id)를, 실패하면 None을 반환합니다.

    Args:
        group_id (str): 미리 생성된 oas_group_id
        info_id (str): 미리 생성된 oas_info_id

    Returns:
        Optional[int]: 객체 생성에 성공하면 생성된 객체의 id, 실패하면 None.
    """

    current_date = timezone.now().date()

    try:
        # 1. OasInfo.objects.create()는 새로 생성된 인스턴스를 반환합니다.
        new_oas_group = OasGroup.objects.create(
            oas_group_id = group_id,
            oas_info_id = info_id,
            oas_name = None,
            created_at = current_date
        )

        return new_oas_group.id

    # 데이터베이스 제약 조건 위반 (예: deviceId unique_together 위반 등)
    except (IntegrityError, DatabaseError) as e:
        print(f"OasGroup 객체 생성 중 데이터베이스 오류 발생: {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=None,
            level='ERROR',
            event_type='OasGroupCreateObject',
            message=f"OasGroup 객체 생성 중 데이터베이스 오류 발생",
            request_data=f"{e}"
        )

        return None
    # 기타 예외 (예: 필드 누락 등)
    except Exception as e:
        print(f"OasGroup 객체 생성 중 알 수 없는 오류 발생: {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=None,
            level='ERROR',
            event_type='OasGroupCreateObject',
            message=f"OasGroup 객체 생성 중 오류 발생",
            request_data=f"{e}"
        )
        return None