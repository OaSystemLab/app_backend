from rest_framework import serializers
from datetime import datetime

class DeviceSearchSerializer(serializers.Serializer):
    sitecode = serializers.CharField(min_length=10, max_length=20)

    # 1. select_clause: 빈 리스트([]) 및 null 허용
    select_clause = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        allow_null=True,
        default=[]
    )

    # 2. data_type: 신규 choices 추가 (예: daily, minutely 등)
    data_type = serializers.ChoiceField(
        choices=['hourly', 'row', 'day', 'night', 'day_night'],
        allow_blank=True,  # "" 입력 허용
        required=False    # 필드 자체가 없는 경우 허용
    )

    # 3. start_time, end_time: null 및 공백 허용
    # input_formats에 ''를 추가하거나 validate에서 처리하여 "" 유입에 대비합니다.
    start_time = serializers.DateTimeField(
        format='%Y-%m-%d %H:%M:%S',
        input_formats=['%Y-%m-%d %H:%M:%S', ''],
        required=False,
        allow_null=True
    )
    end_time = serializers.DateTimeField(
        format='%Y-%m-%d %H:%M:%S',
        input_formats=['%Y-%m-%d %H:%M:%S', ''],
        required=False,
        allow_null=True
    )

    def validate(self, data):
        data_type = data.get('data_type')
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        # 조건부 검증: 특정 data_type에서는 시간이 필수인 경우 예외 처리
        # 만약 'hourly'나 'history'일 때만 시간이 필수라면 아래와 같이 작성합니다.
        time_dependent_types = ['hourly', 'row']

        if data_type in time_dependent_types:
            if not start_time or not end_time:
                raise serializers.ValidationError({
                    "start_time": f"{data_type} 타입에서는 시작/종료 시간이 필수입니다."
                })

            if start_time > end_time:
                raise serializers.ValidationError("종료 시간은 시작 시간보다 빨라야 합니다.")

        return data

class DashboardSerializer(serializers.Serializer):
    # 사용자 등록 도지 않은 사이트드가 오면?
    sitecode = serializers.CharField(min_length=10, max_length=20)

    data_type = serializers.ChoiceField(
        choices=['a1', 'a2', 'a3'],
        required=False,
        allow_blank=True
    )

