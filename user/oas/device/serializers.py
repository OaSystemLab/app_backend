# oas/auth/device/serializers.py

import json
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import OasGroup, OasInfo # 같은 디렉토리의 models.py에서 모델 import
#from account.models import UserInfo, UserEmail

from log_events.models import ProjectLogEntry # ⭐️ 통합 모델 임포트
# datetime 모듈 대신 Django의 timezone을 사용하는 것이 더 안전하고 일반적입니다.
# from django.utils import timezone
# from django.db import IntegrityError, DatabaseError
# from typing import Optional # 반환 타입 힌트를 위해 Optional 임포트

#from account.utils.usergroup_manager import UserGroupManager

#from .utils.oas_manager import OasInfoSearchDeviceIdLock, OasInfoNewObject, OasGroupCreateObject, OasInfoDelete
from .utils.oas_setup_service import OasSetupService
from django.core.validators import RegexValidator

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
        #fields = '__all__' # 모든 필드를 포함하여 모델 변경 사항에 유연하게 대응
        fields = (
            'id',
            'site',
            'dong',
            'ho',
            'oas_id',
            'deviceId',
            'room',
            'auth',
            # 필요한 다른 필드도 추가
        )
        read_only_fields = ['id', 'created_at']


# ----------------------------------------------------------------------
# 3. Auth Request Serializer (인증 요청 데이터 처리)
# ----------------------------------------------------------------------
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
    deviceId = serializers.CharField(max_length=100, help_text="환경 제어기 Device ID")

    # 요청 받은 create_date 문자열을 처리합니다.
    # 사용자가 제시한 'YYYY.MM.DD.HH:MM' 형식에 맞추어 format을 지정합니다.
    # Timezone 정보가 없는 순수 DateTimeField로 처리합니다.
    # create_date = serializers.DateTimeField(
    #     format="%Y.%m.%d.%H:%M",
    #     input_formats=["%Y.%m.%d.%H:%M"],
    #     help_text="요청 생성 날짜 및 시간 (예: 2025.11.24.15:27)",
    #     null=True,
    #     blank=True,
    # )

    # 현재 검증 중인 'id' 필드의 값은 'data' 변수에 있습니다.
    def validate_id(self, data):

        user = self.context['request'].user
        oas_group_id = None

        # ✅ 체크. UserEmail 의 내용이 없는 경우 (무조건 있어야 하는 곳인데 없으면 문제가 생기기 때문에 처리 함.)
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
        if user.oas_group_id is None :  # 없으면
            try:
                oas_group_id = OasSetupService.setup_new_group(user, self.initial_data)
            except Exception as e:
                # 서비스에서 발생한 오류를 받아서 ValidationError로 변환
                print(f"❌ OAS 그룹 설정 서비스 오류 발생: {e}")
                raise ValidationError({"detail": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})
        else :
            try:
                oas_group_id = OasSetupService.setup_update_group(user, self.initial_data)
            except Exception as e:
                # 서비스에서 발생한 오류를 받아서 ValidationError로 변환
                print(f"❌ OAS 그룹 설정 서비스 오류 발생: {e}")
                raise ValidationError({"detail": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})


        return data


# ----------------------------------------------------------------------
# 4. oas_info 방이름 변경
# ----------------------------------------------------------------------
class OasInfoRoomUpdateSerializer(serializers.Serializer):
    """
    OasInfo의 'room' 필드 수정을 위한 요청 데이터 시리얼라이저
    """
    # 수정할 OasInfo 객체를 식별하기 위한 ID
    oas_info_id = serializers.IntegerField(
        label="OasInfo ID",
        help_text="수정할 OasInfo 객체의 Primary Key (ID)"
    )
    # 새로 설정할 방 이름
    new_room_name = serializers.CharField(
        label="새 방 이름",
        max_length=100, # OasInfo 모델의 room 필드 max_length에 맞춰주세요
        help_text="OasInfo에 설정할 새로운 방 이름"
    )

    def validate_new_room_name(self, value):
        # 방 이름에 대한 추가적인 유효성 검사 로직을 여기에 추가할 수 있습니다.
        if not value.strip():
            raise serializers.ValidationError("방 이름은 공백일 수 없습니다.")
        return value

# ----------------------------------------------------------------------
# 5.  UserAppOasRequest json 내용 검즘
# ----------------------------------------------------------------------
class OptionSerializer(serializers.Serializer):
    # air, timer 등은 상황에 따라 필수일 수도, 아닐 수도 있으므로 required=False 설정
    air = serializers.CharField(required=False, allow_blank=True)
    timer = serializers.CharField(required=False, allow_blank=True)

    # 리스트 형태 검증: 정수(Integer)가 담긴 리스트이며, 길이는 정확히 24개여야 함
    reservation = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=3), # 0~3 사이 값 가정
        min_length=0,
        max_length=24,
        required=False,
        allow_empty=True
    )
class SleepModeSerializer(serializers.Serializer):
    # air, timer 등은 상황에 따라 필수일 수도, 아닐 수도 있으므로 required=False 설정
    moodlampoff = serializers.ChoiceField(choices=["on", "off"], allow_blank=True)
    diallampoff = serializers.ChoiceField(choices=["on", "off"], allow_blank=True)

    # 시간 정규식 수정: [0-1]? 를 사용하여 한 자리 숫자 시간도 허용
    time_regex = RegexValidator(
        regex=r'^([0-1]?\d|2[0-3]):([0-5]\d)$',
        message="시간 형식은 HH:MM 또는 H:MM 이어야 합니다 (예: 10:00, 8:00)."
    )

    bedtime = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[time_regex]
    )
    wakeuptime = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[time_regex]
    )

class UserAppRequsetSerializer(serializers.Serializer):
    sitecode = serializers.CharField(min_length=17, max_length=18)

    type = serializers.ChoiceField(choices=["sensing", "aircontrol", "ledcontrol", "lcdcontrol",
                                            "ventcontrol", "uservent", "sleepmode"])
    action = serializers.ChoiceField(choices=["on", "off",
                                              "all_on", "all_off", "diffu_on", "diffu_off",
                                              "auto", "breeze", "weak", "strong",
                                              "air", "timer", "reservation", "none"])
    option = OptionSerializer(required=False)
    sleep = SleepModeSerializer(required=False, allow_null=True)


    def validate_sitecode(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("sitecode는 숫자로만 구성되어야 합니다.")
        return value
