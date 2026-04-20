# 인증 및 계정 생성

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed

from django.utils import timezone
from datetime import timedelta
from django.db import transaction

from ..models import UserInfo
from oas.device.models import OasGroup, OasInfo

from approval.models import ApprovalRequest, ApprovalStatus
from approval.serializers import ApprovalRequestSerializer, LightApprovalRequestSerializer

# tdengine
from tdengine.services import td_service, db_service

# ----------------------------------------------------------------------
# 1. 사용자 등록 Serializer
# ----------------------------------------------------------------------
class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    UserInfo 모델 기반의 사용자 등록 Serializer.

    입력 필드: email, password, password2, nick_name
    """
    password1 = serializers.CharField(
        write_only=True, required=True, style={'input_type': 'password'}, label=_("비밀번호")
    )
    password2 = serializers.CharField(
        write_only=True, required=True, style={'input_type': 'password'}, label=_("비밀번호 확인")
    )

    class Meta:
        model = UserInfo
        fields = ('email', 'nick_name', 'password1', 'password2')
        read_only_fields = ('is_active', 'is_staff', 'is_superuser')

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError({"password2": _("비밀번호가 일치하지 않습니다.")})

        data.pop('password2')

        try:
            validate_password(data['password1'], user=None)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError({"password1": list(e.messages)})

        return data

    def create(self, validated_data):
        user = UserInfo.objects.create_user(
            email=validated_data['email'],
            nick_name=validated_data['nick_name'],
            password=validated_data['password1']
        )
        return user

# ----------------------------------------------------------------------
# 2. 사용자 로그인 Serializer
# ----------------------------------------------------------------------
class UserLoginSerializer(serializers.Serializer):
    """ 사용자 로그인을 위한 Serializer. """
    email = serializers.EmailField(max_length=255, label=_("이메일"))
    password = serializers.CharField(max_length=128, write_only=True, style={'input_type': 'password'}, label=_("비밀번호"))

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError({"detail": "이메일과 비밀번호는 필수 입력 항목입니다."})

        return data


# ----------------------------------------------------------------------
# 3. JWT 토큰 Serializer (Custom) -- login
# ----------------------------------------------------------------------
UNLOCK_DELAY = timedelta(minutes=15)
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    # @classmethod
    # def get_token(cls, user):
    #     token = super().get_token(user)
    #     #token['user_id'] = user.id
    #     token['nick_name'] = user.nick_name
    #     #token['oas_auth'] = False

    #     if hasattr(user, 'email_info'):
    #          token['email_auth'] = user.email_info.email_auth
    #     else:
    #          token['email_auth'] = False

    #     token['family_group_id'] = user.family_group_id
    #     token['family_level'] = user.family_level

    #     # approval(승인 요청)
    #     # 1. PENDING 요청 목록 조회
    #     pending_requests = ApprovalRequest.objects.filter(
    #         approver=user,
    #         status=ApprovalStatus.PENDING
    #     ).order_by('requested_at')

    #     # 2. 요청 존재 여부 확인
    #     has_pending_requests = pending_requests.exists()

    #     # 3. 요청 목록 직렬화
    #     # 토큰 페이로드 크기를 줄이기 위해, 필요하다면 경량 Serializer를 정의하여 사용하세요.
    #     # 여기서는 ApprovalRequestSerializer를 사용한다고 가정합니다.

    #     # list를 넣기 때문에 many=True로 설정
    #     serializer = ApprovalRequestSerializer(pending_requests, many=True)

    #     # 4. 토큰 페이로드에 추가
    #     # 'family_auth_approval' 대신 의미가 더 명확한 키를 사용하는 것이 좋습니다.
    #     # 예: 'pending_approvals' 또는 'approvals_as_master'

    #     token['approval_status'] = has_pending_requests
    #     token['approval_list'] = serializer.data

    #     user_oas_groups = OasGroup.objects.filter(
    #         oas_group_id=user.oas_group_id
    #     ).select_related('oas_info')

    #     # 이제 루프를 돌며 상세 정보(OasInfo)에 접근할 수 있습니다.
    #     dev_list = []  # sitecode들을 담을 빈 리스트(배열)
    #     for group in user_oas_groups:
    #         #print(f"group: {group.oas_info}")
    #         sitecode = group.oas_info.site+group.oas_info.dong+group.oas_info.ho+group.oas_info.oas_id
    #         #print(f"sitecode: {sitecode}")
    #         dev_list.append({
    #             'id' : group.oas_info.oas_id,
    #             'sitecode' : sitecode,
    #             'room_name' : group.oas_info.room,
    #             'data' : td_service.get_latest_data(sitecode)
    #         })

    #     token['dev'] = dev_list

    #     return token
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token['nick_name'] = user.nick_name
        if hasattr(user, 'email_info'):
             token['email_auth'] = user.email_info.email_auth
        else:
             token['email_auth'] = False
        token['family_group_id'] = user.family_group_id
        token['family_level'] = user.family_level


        return token

    def validate(self, attrs):
        # 1. 🔍 이메일을 이용해 사용자 객체를 먼저 가져옵니다.
        #    사용자 객체를 가져오지 못하면 기본 인증 실패로 처리합니다.
        email = attrs.get(UserInfo.USERNAME_FIELD)
        try:
            user = UserInfo.objects.get(**{UserInfo.USERNAME_FIELD: email})
        except UserInfo.DoesNotExist:
            # 존재하지 않는 이메일일 경우, 보안을 위해 일반 인증 실패 메시지 반환
            raise serializers.ValidationError({
                "detail": "제공된 인증 정보가 유효하지 않습니다. 이메일 또는 비밀번호를 확인해 주세요."
            })

        # --- 🛡️ 2. is_active 확인 및 잠금 해제/차단 로직 ---
        if not user.is_active:
            # 계정이 잠겨 있는 경우 (is_active=False)
            last_fail_time = user.last_fail_time
            current_time = timezone.now()

            if last_fail_time and (current_time >= last_fail_time + UNLOCK_DELAY):
                # 15분 경과: 계정 잠금 해제 및 카운트 초기화
                with transaction.atomic():
                    user.is_active = True
                    user.decryption_fail_count = 0
                    user.last_fail_time = None
                    user.save(update_fields=['is_active', 'decryption_fail_count', 'last_fail_time'])
                    # 계정 잠금 해제 후, 이제 비밀번호 인증 단계로 넘어갑니다.
            else:
                # 15분 미경과: 잠금 상태 유지 및 에러 발생 -> 토큰 발급 차단
                remaining_time = (last_fail_time + UNLOCK_DELAY) - current_time if last_fail_time else UNLOCK_DELAY

                # 명확한 계정 잠금 메시지 반환
                raise serializers.ValidationError({
                    "detail": f"해당 계정은 잠겨 있습니다. 잠금 해제까지 약 {int(remaining_time.total_seconds() // 60) + 1}분 남았습니다."
                })
        # --- 🛡️ 3. 잠금 해제 로직 종료 ---

        # 4. 🔑 비밀번호 검증 및 토큰 발급 준비 (is_active가 True로 확인/전환된 상태)
        #    이제 super().validate가 실행되어 비밀번호가 맞는지 확인합니다.
        try:
            # super().validate가 성공적으로 실행되면 self.user에 user 객체가 할당됩니다.
            data = super().validate(attrs)
        except AuthenticationFailed:
            # 비밀번호가 틀린 경우에만 이곳으로 옵니다.
            raise serializers.ValidationError({
                "detail": "제공된 인증 정보가 유효하지 않습니다. 이메일 또는 비밀번호를 확인해 주세요."
            })


        user = self.user
        #data['user_id'] = user.id
        data['nick_name'] = user.nick_name
        #data['oas_auth'] = False

        if hasattr(user, 'email_info'):
             data['email_auth'] = user.email_info.email_auth
        else:
             data['email_auth'] = False
        data['family_group_id'] = user.family_group_id
        data['family_level'] = user.family_level
        # approval(승인 요청)
        # approval(승인 요청)
        # 1. PENDING 요청 목록 조회
        pending_requests = ApprovalRequest.objects.filter(
            approver=user,
            status=ApprovalStatus.PENDING
        ).order_by('requested_at')

        # 2. 요청 존재 여부 확인
        has_pending_requests = pending_requests.exists()

        # 3. 요청 목록 직렬화
        # 토큰 페이로드 크기를 줄이기 위해, 필요하다면 경량 Serializer를 정의하여 사용하세요.
        # 여기서는 ApprovalRequestSerializer를 사용한다고 가정합니다.

        # list를 넣기 때문에 many=True로 설정
        serializer = LightApprovalRequestSerializer(pending_requests, many=True)

        # 4. 토큰 페이로드에 추가
        # 'family_auth_approval' 대신 의미가 더 명확한 키를 사용하는 것이 좋습니다.
        # 예: 'pending_approvals' 또는 'approvals_as_master'

        data['approval_status'] = has_pending_requests
        data['approval_list'] = serializer.data

        user_oas_groups = OasGroup.objects.filter(
            oas_group_id=user.oas_group_id
        ).select_related('oas_info')

        # 이제 루프를 돌며 상세 정보(OasInfo)에 접근할 수 있습니다.
        dev_list = []  # sitecode들을 담을 빈 리스트(배열)
        for group in user_oas_groups:
            #print(f"group: {group.oas_info}")
            sitecode = group.oas_info.site+group.oas_info.dong+group.oas_info.ho+group.oas_info.oas_id
            #print(f"sitecode: {sitecode}")
            h_status, tsring, last_seen =  db_service.get_heartbeat_status(sitecode)

            dev_list.append({
                'id' : group.oas_info.oas_id,
                'sitecode' : sitecode,
                'room_name' : group.oas_info.room,
                'status' : h_status,
                'tsring' : tsring,
                'last_seen' : last_seen,
                'data' : db_service.redis_get_sensing(sitecode)
            })
            #db_service.tdredis_get_sensing(sitecode)

        #print(f"dev_list : {dev_list}")

        data['dev'] = dev_list



        return data