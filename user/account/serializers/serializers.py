from rest_framework import serializers
from ..models import UserInfo

# ----------------------------------------------------------------------
# 1. UserInfo List Serializer
# ----------------------------------------------------------------------
class UserInfoListSerializer(serializers.ModelSerializer):
    """
    OasIUserInfonfo 모델을 위한 Serializer.
    환경 제어기의 상세 정보 (지역 코드, 인증 상태 등)를 처리합니다.
    """
    class Meta:
        model = UserInfo
        #fields = '__all__' # 모든 필드를 포함하여 모델 변경 사항에 유연하게 대응
        fields = (
            'id',
            'email',
            'family_level',
            'nick_name',
        )
        read_only_fields = ['email', 'family_level']

# ----------------------------------------------------------------------
# 2. UserInfo Nick Name Serializer..
# ----------------------------------------------------------------------
class UserInfoNicknameUpdateSerializer(serializers.Serializer):
    """
    UserInfo nick_name 필드 수정을 위한 요청 데이터 시리얼라이저
    """
    # 새로 설정할 닉 네임
    nick_name = serializers.CharField(
        label="새로운 닉 네임",
        max_length=100, # UserInfo 모델의 nick_name 필드 max_length에 맞춰주세요
        help_text="UserInfo에 설정할 새로운 닉 네임"
    )

    def validate_new_room_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("공백일 수 없습니다.")
        return value

 # ----------------------------------------------------------------------
# 3. 마스터 권한 변경.
# ----------------------------------------------------------------------
class MasterTransferSerializer(serializers.Serializer):
    """마스터 권한을 넘겨받을 사용자(새 마스터)의 PK를 위한 시리얼라이저"""
    new_master_user_id = serializers.IntegerField(
        required=True,
        help_text="새 마스터 권한을 부여할 대상 사용자(UserInfo)의 고유 ID(PK)"
    )

    def validate_new_master_user_id(self, value):
        if value is None:
            raise serializers.ValidationError("새 마스터의 사용자 ID는 필수 값입니다.")
        # 추가적인 유효성 검사 (예: 음수 방지)
        if value <= 0:
             raise serializers.ValidationError("유효하지 않은 사용자 ID입니다.")
        return value
 # ----------------------------------------------------------------------
# 3. 가족 그룹 추방
# ----------------------------------------------------------------------
class MemberKickSerializer(serializers.Serializer):
    """멤버 추방을 위한 대상 사용자 PK를 위한 시리얼라이저"""
    target_user_id = serializers.IntegerField(
        required=True,
        help_text="그룹에서 추방할 대상 사용자(UserInfo)의 고유 ID(PK)"
    )

    def validate_target_user_id(self, value):
        if value is None or value <= 0:
             raise serializers.ValidationError("유효하지 않은 사용자 ID입니다.")
        return value