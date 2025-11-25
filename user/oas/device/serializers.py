# oas/auth/device/serializers.py

import json
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import OasGroup, OasInfo # 같은 디렉토리의 models.py에서 모델 import
from account.models import UserInfo, UserEmail

from log_events.models import ProjectLogEntry # ⭐️ 통합 모델 임포트
# datetime 모듈 대신 Django의 timezone을 사용하는 것이 더 안전하고 일반적입니다.
from django.utils import timezone
from django.db import IntegrityError, DatabaseError
from typing import Optional # 반환 타입 힌트를 위해 Optional 임포트
# ----------------------------------------------------------------------
# 1. OasGroup Serializer (환경 제어기 그룹 정보)
# ----------------------------------------------------------------------
class OasGroupSerializer(serializers.ModelSerializer):
    """
    OasGroup 모델을 위한 Serializer.
    주로 등록된 환경 제어기 그룹 정보를 읽거나 생성하는 데 사용됩니다.
    """
    class Meta:
        model = OasGroup
        fields = [
            'id',             # Django 자동 생성 PK
            'oas_group_id',
            'oas_info_id',
            'oas_name',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at'] # 자동으로 관리되는 필드

# ----------------------------------------------------------------------
# 2. OasInfo Serializer (환경 제어기 상세 정보)
# ----------------------------------------------------------------------
class OasInfoSerializer(serializers.ModelSerializer):
    """
    OasInfo 모델을 위한 Serializer.
    환경 제어기의 상세 정보 (지역 코드, 인증 상태 등)를 처리합니다.
    """
    class Meta:
        model = OasInfo
        fields = '__all__' # 모든 필드를 포함하여 모델 변경 사항에 유연하게 대응
        read_only_fields = ['id', 'created_at']


# ----------------------------------------------------------------------
# 3. Auth Request Serializer (인증 요청 데이터 처리)
# ----------------------------------------------------------------------
def OasInfoSearchDeviceIdLock(device_id : str):
    """
    주어진 device_id와 일치하는 OasInfo 레코드를 찾아 잠금(lock=True) 상태로 업데이트합니다.

    Args:
        device_id (str): 업데이트할 환경 제어기의 Device ID 값.
    """

    # 1. 현재 날짜를 가져옵니다. (OasInfo 모델의 lock_date가 DateField이므로 date 객체를 사용)
    current_date = timezone.now().date()

    # 2. filter()를 사용하여 쿼리셋을 선택하고, update()를 사용하여 일괄 업데이트를 수행합니다.
    # update()는 데이터베이스 레벨에서 바로 실행되므로 매우 빠릅니다.
    OasInfo.objects.filter(deviceId=device_id).update(
        lock=True,              # lock 필드를 True로 설정
        lock_date=current_date  # lock_date 필드를 현재 날짜로 설정
    )
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
        # 오류 발생 시 False 반환
        return None
    # 기타 예외 (예: 필드 누락 등)
    except Exception as e:
        print(f"OasInfo 객체 생성 중 알 수 없는 오류 발생: {e}")
        return None


class AuthRequestSerializer(serializers.Serializer):
    """
    환경 제어기 인증 요청 시 클라이언트로부터 받는 JSON 데이터를 처리하는 Serializer입니다.
    Model과 직접 연결되지 않고, 데이터의 유효성 검사만을 위해 사용됩니다.
    """
    # CharField는 문자열 데이터에 사용됩니다.
    site = serializers.CharField(max_length=10, help_text="지역 코드")
    dong = serializers.CharField(max_length=4, help_text="아파트 동")
    ho = serializers.CharField(max_length=4, help_text="아파트 호")
    # 'oas_id' 모델 필드와 일치시키기 위해 'oas_id'로 변환될 수 있도록 'source' 설정도 고려할 수 있지만,
    # 여기서는 받은 데이터 그대로 'id'를 사용합니다.
    id = serializers.CharField(max_length=2, help_text="환경 제어기 ID")
    deviceId = serializers.CharField(max_length=20, help_text="환경 제어기 Device ID")

    # 요청 받은 create_date 문자열을 처리합니다.
    # 사용자가 제시한 'YYYY.MM.DD.HH:MM' 형식에 맞추어 format을 지정합니다.
    # Timezone 정보가 없는 순수 DateTimeField로 처리합니다.
    create_date = serializers.DateTimeField(
        format="%Y.%m.%d.%H:%M",
        input_formats=["%Y.%m.%d.%H:%M"],
        help_text="요청 생성 날짜 및 시간 (예: 2025.11.24.15:27)"
    )

    # 현재 검증 중인 'id' 필드의 값은 'data' 변수에 있습니다.
    def validate_id(self, data):

        user = self.context['request'].user
        oas_group_id = None

        # ☑️ 예외. UserEmail 의 내용이 없는 경우 (무조건 있어야 하는 곳인데 없으면 문제가 생기기 때문에 처리 함.)
        if user.email_info is None :
            ProjectLogEntry.objects.create(
                app_name='oas.device',
                user=user,
                level='WARNING',
                event_type='AuthRequestSerializer',
                message=f"사용자의 UserEmail 정보가 없습니다. 사용자 점검 및 수정이 필요 합니다.",
                request_data=json.dumps(self.initial_data, ensure_ascii=False)
            )
            raise ValidationError({"detail": "사용자 이메일 인증 정보가 누락되었습니다."})
        # ✅ 체크. 이메일 인증 미사용자 처리
        if user.email_info.email_auth is False :
            raise ValidationError({"detail": "이메일 인증을 하지 않은 상태 입니다. 인증 후 다시 해주세요."})

        # ⭐조건. oas_group_id 있는 경우와 없는 경우 처리
        if user.oas_group_id is None :
            # 1. oas_group_id 만들기
            oas_group_id = "oas_group_" + str(user.id)
            # 2. deviceId 전부 Lock 처리
            OasInfoSearchDeviceIdLock(self.initial_data['deviceId'])
            # 3. oas_info 생성
            oas_info_id = OasInfoNewObject(self.initial_data)

        return data