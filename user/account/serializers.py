# serializers.py 파일은 **Django REST Framework (DRF)**에서 사용하는 핵심 구성 요소로,
# 주로 데이터 변환 및 유효성 검사의 역할을 담당합니다.

# UserRegistrationSerializer는 사용자 등록을 위한 역직렬화 및 생성에 초점을 맞추고 있습니다.

# 입력 데이터 정의:
# API 요청에서 email, nick_name, password, password2 네 가지 필드만 받도록 정의합니다.
# (모델에 있는 다른 필드들은 자동으로 처리되거나 기본값으로 설정됨)

# 유효성 검사 (Validation):
# 필수 유효성: password와 password2가 서로 일치하는지 확인합니다.
# 모델 유효성: email이나 nick_name이 이미 DB에 존재하는지 등 모델 수준의 제약 조건을 검사합니다.

# 모델 생성 (.create()):
# 유효성 검사를 통과한 데이터를 바탕으로 UserInfo 객체를 실제로 생성합니다.
# 이때 password 필드는 반드시 해시(암호화) 처리하여 안전하게 저장하도록 처리합니다.

# 요약하자면, serializers.py는 **클라이언트(브라우저/앱)**와 Django 서버 사이에서 오가는 데이터를 검증하고,
# 파이썬 객체와 웹 통신 형식(JSON) 사이를 번역해주는 통로 관리자 역할을 합니다.


from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from django.utils.translation import gettext_lazy as _
from .models import UserInfo , OasGroup, UserEmail
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import ValidationError as DRFValidationError


from django.utils import timezone
from datetime import timedelta
from django.db import transaction

from .tasks import send_auth_email_task # Celery Task import

import random
# ----------------------------------------------------------------------
# 1. 사용자 등록 View
# ----------------------------------------------------------------------
class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    UserInfo 모델 기반의 사용자 등록 Serializer.
    입력 필드: email, password, password2, nick_name
    """
    # password1과 password2를 write_only 필드로 추가 (응답에 포함되지 않음)
    password1 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        label=_("비밀번호")
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        label=_("비밀번호 확인")
    )

    class Meta:
        model = UserInfo
        # 클라이언트로부터 입력받을 필드 목록
        fields = ('email', 'nick_name', 'password1', 'password2')
        # 읽기 전용 필드 (선택 사항이지만 명확히 하기 위해 추가)
        read_only_fields = ('is_active', 'is_staff', 'is_superuser')

    def validate(self, data):
        """
        password1와 password2의 일치 여부를 확인하고,
        Django의 기본 비밀번호 유효성 검사를 수행합니다.
        """
        if data['password1'] != data['password2']:
            raise serializers.ValidationError({"password2": _("비밀번호가 일치하지 않습니다.")})

        # password2는 모델에 저장할 필요가 없으므로 삭제합니다.
        data.pop('password2')

        # Django의 기본 비밀번호 유효성 검사 적용 (settings.AUTH_PASSWORD_VALIDATORS)
        try:
            # UserInfo 인스턴스가 아직 없으므로 None을 전달합니다.
            validate_password(data['password1'], user=None)
        except exceptions.ValidationError as e:
            # 유효성 검사 오류 발생 시 DRF 에러로 변환하여 응답
            raise serializers.ValidationError({"password1": list(e.messages)})

        return data

    def create(self, validated_data):
        """
        검증된 데이터를 사용하여 새로운 UserInfo 인스턴스를 생성하고 비밀번호를 해시합니다.
        family_level 등 나머지 필드는 models.py에 정의된 기본값이 사용됩니다 ('none', '0' 등).
        """
        user = UserInfo.objects.create_user(
            email=validated_data['email'],
            nick_name=validated_data['nick_name'],
            password=validated_data['password1']
            # create_user 메서드는 models.py의 UserInfoManager에 정의되어 있습니다.
            # 이외의 모든 필드(family_level, family_auth_count 등)는 기본값이 적용됩니다.
        )
        return user

# ----------------------------------------------------------------------
# 2. 사용자 로그인 View (추가)
# ----------------------------------------------------------------------
class UserLoginSerializer(serializers.Serializer):
    """
    사용자 로그인을 위한 Serializer.
    입력 필드: email, password
    로그인 시도는 view에서 처리하며, 이 Serializer는 데이터의 형식과 유효성만 검사합니다.
    """
    email = serializers.EmailField(
        max_length=255,
        label=_("이메일")
    )
    password = serializers.CharField(
        max_length=128,
        write_only=True,
        style={'input_type': 'password'},
        label=_("비밀번호")
    )

    def validate(self, data):
        """
        입력된 데이터의 기본적인 형식 유효성을 검사합니다.
        (실제 사용자 인증은 view나 별도의 인증 백엔드에서 수행하는 것이 일반적입니다.)
        """
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError({"detail": "이메일과 비밀번호는 필수 입력 항목입니다."})

        # 추가적인 복잡한 인증(DB 조회, 암호 비교)은 view나 custom authenticate()에서 처리
        return data


# ----------------------------------------------------------------------
# 3. api/token 이용한 로그인시 전달 해 줄 정보
# ----------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # 부모 클래스의 get_token을 호출하여 Access 및 Refresh 토큰 객체를 생성합니다.
        token = super().get_token(user)

        # 토큰의 페이로드에 원하는 사용자 정보를 추가합니다.
        # 일반적으로 'user_id' 또는 'id'를 사용합니다.
        # 여기서는 UserInfo 모델의 id 값을 추가합니다.
        token['user_id'] = user.id  # user는 인증된 UserInfo 인스턴스입니다.
        token['nick_name'] = user.nick_name # 닉네임도 추가 가능
        token['oas_auth'] = False

        # UserEmail 모델의 이메일 인증 상태를 추가합니다.
        # related_name='email_info'로 접근합니다.
        if hasattr(user, 'email_info'):
             token['email_auth'] = user.email_info.email_auth
        else:
             token['email_auth'] = False # UserEmail 레코드가 없는 경우를 대비

        return token

    def validate(self, attrs):
        try:
            # 부모 클래스의 validate 메서드를 호출하여 토큰 쌍을 얻습니다.
            # 이 과정에서 인증(authenticate)이 실패하면 AuthenticationFailed 예외가 발생합니다.
            data = super().validate(attrs)
        except AuthenticationFailed:
            # === 이 부분을 수정합니다! ===
            # 인증 실패 시 발생하는 AuthenticationFailed를 가로채고,
            # Custom Validation Error를 발생시켜 non_field_errors를 커스텀합니다.
            raise serializers.ValidationError({
                "detail": "제공된 인증 정보가 유효하지 않습니다. 이메일 또는 비밀번호를 확인해 주세요."
            })

        # 사용자 ID를 응답 데이터에 직접 추가합니다.
        # self.user는 TokenObtainPairSerializer의 validate 과정에서 설정됩니다.
        data['user_id'] = self.user.id
        data['nick_name'] = self.user.nick_name
        data['oas_auth'] = False

        # family_group_id도 추가
        #data['family_group_id'] = self.user.family_group_id

        # UserEmail 모델의 이메일 인증 상태를 응답에 포함합니다.
        if hasattr(self.user, 'email_info'):
             data['email_auth'] = self.user.email_info.email_auth
        else:
             data['email_auth'] = False

        return data

# ----------------------------------------------------------------------
# 4. 임시 2025.10.27 View (삭제 필요...)
# ----------------------------------------------------------------------
class OasGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = OasGroup
        # API 응답에 포함할 필드를 지정합니다.
        # 모든 필드를 포함하려면 '__all__'을 사용하거나, 필요한 필드만 리스트로 지정합니다.
        fields = [
            'oas_group_id',
            'oas_info_id',
            'oas_name',
            'created_at'
        ]
        # 또는 fields = '__all__'

# ----------------------------------------------------------------------
# 5. email 인증 코드 요청 하기 전에 검증 하는 부분
# ----------------------------------------------------------------------
class EmailAuthSendSerializer(serializers.Serializer):
    """
    로그인된 사용자의 정보를 사용하여 이메일 인증 코드를 전송하기 위한 Serializer입니다.
    """

    def validate(self, data):
        # View에서 self.request.user를 context로 넘겨받는다고 가정합니다.
        # context['request']는 view에서 self.get_serializer_context()를 통해 넘어와야 함.
        request = self.context.get('request')

        if not request:
            raise DRFValidationError("요청 객체를 context에서 찾을 수 없습니다. View 설정을 확인하세요.")

        user = request.user

        # 1. 사용자 객체 인증 여부 확인
        if not user.is_authenticated:
            # DRFValidationError를 사용하여 detail 메시지 반환
            raise DRFValidationError(
                {"detail": "요청을 처리하려면 유효한 로그인 토큰이 필요합니다."},
                code='not_authenticated'
            )

        # 2. UserEmail 객체 조회 (일반적으로 user 모델에 OnetoOne으로 연결되어 있다고 가정)
        try:
            # UserEmail 모델명을 가정합니다. 실제 모델명으로 변경하세요.
            email_info = user.email_info
        except Exception: # UserEmail.DoesNotExist 대신 일반 예외 처리
            # UserEmail 모델명 import 후 UserEmail.DoesNotExist를 사용하는 것이 더 정확합니다.
            raise DRFValidationError(
                {"detail": "계정에 연결된 인증 정보가 누락되었습니다. 관리자에게 문의해 주세요."},
                code='missing_email_info'
            )

        # 3. 이미 인증이 완료되었는지 확인 (주석 해제 시)
        # if email_info.email_auth:
        #     raise DRFValidationError(
        #         {"detail": "이미 이메일 인증이 완료된 계정입니다."},
        #         code='already_verified'
        #     )

        # 4. 인증 잠금 상태 확인 및 잠금 해제 조건 검사 (DB 수정 제외)

        # 예외 상황 발생
        # 이슈. email_auth_lock 값이 있으나 email_lock_time 없는 경우 발생
        #      위 같은 상황이면 계속 해서 잠김 상태로 가게 됨.
        # TODO.  email_auth_lock, email_lock_time 둘 중에 하나만 있는경우 처리 방안은?
        #        email_auth_lock True email_lock_time None 경우는 email_auth_lock 해제 하고 처음 부터 하게함
        #        email_auth_lock False email_lock_time 있는 경우는 email_lock_time 초기화

        # 버그성 이슈 처리
        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is True and email_info.email_lock_time is None :
            print("버그 이슈 email_refresh_count > 3 , email_auth_lock is True,email_lock_time is None ")
            self.context['email_info'] = email_info
            return data

        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is False and email_info.email_lock_time is not None :
            print("버그 이슈 email_refresh_count > 3, email_auth_lock is False,email_lock_time is not None ")
            self.context['email_info'] = email_info
            return data

        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is False and email_info.email_lock_time is  None :
            print("버그 이슈 email_refresh_count > 3, email_auth_lock is False,email_lock_time is None ")
            self.context['email_info'] = email_info
            return data


        # **A. 현재 잠금 상태인지 확인**
        if email_info.email_auth_lock:
            # 잠금 해제 조건: 5분이 경과했는지 확인
            print("email_info.email_auth_lock.")
            if email_info.email_lock_time and (timezone.now() - email_info.email_lock_time) > timedelta(minutes=5):
                # 5분 경과: 잠금 해제 가능 상태. View에서 DB 수정 처리
                print("유효성 검사 통과")
                self.context['email_info'] = email_info
                return data
            else:
                # 5분 미경과: 여전히 잠금 상태, 오류 발생
                raise DRFValidationError(
                    {
                        "detail": "이메일 재전송 요청 횟수가 초과되어 계정이 잠겼습니다. 5분 후에 다시 시도해 주세요.",
                        "lock_time": email_info.email_lock_time
                    },
                    code='lock_required'
                )

        # **B. 잠금 필요 조건 검사 (카운트 4회 초과)**
        # 현재 잠금 상태가 아니지만, 카운트가 초과된 경우
        if email_info.email_refresh_count > 3:
            # 잠금 상태로 전환해야 함. View에서 DB 수정 처리
            print("잠금 상태")
            raise DRFValidationError(
                {
                    "detail": "이메일 재전송 요청 횟수가 초과되어 계정이 잠겼습니다. 5분 후에 다시 시도해 주세요.",
                    "lock_time": email_info.email_lock_time
                },
                code='lock_required'
            )

        # 유효성 검사를 통과한 UserEmail 객체를 context에 저장하여 view의 create/perform_create에서 사용
        self.context['email_info'] = email_info

        return data # 유효성 검사를 통과한 데이터 반환
# ----------------------------------------------------------------------
# 6. 인증 메일서 받은 코드 검증 하기 전에 체크 하는 부분
# ----------------------------------------------------------------------
class EmailAuthConfirmSerializer(serializers.Serializer):
    """
    사용자로부터 받은 이메일과 인증 코드를 검증하고,
    인증이 완료되면 UserEmail 모델의 상태를 업데이트할 준비를 합니다.
    """
    # email = serializers.EmailField(
    #     max_length=100,
    #     required=True,
    #     label=_("이메일")
    # )
    auth_code = serializers.CharField(
        max_length=10, # UserEmail 모델의 max_length에 맞춰 10으로 설정
        required=True,
        label=_("인증 코드")
    )

    def validate(self, data):
        # View에서 self.request.user를 context로 넘겨받는다고 가정합니다.
        user = self.context['request'].user
        auth_code = data.get('auth_code')

        # 1. 사용자 객체 인증 여부 확인 (View의 Permission 설정으로 걸러지지만 안전을 위해 유지)
        if not user.is_authenticated:
            # DRFValidationError를 사용하여 detail 메시지 반환
            raise DRFValidationError(
                {"detail": "로그인이 필요합니다."},
            )
        # 2. UserEmail 객체 확인
        try:
            email_info = user.email_info
        except UserEmail.DoesNotExist:
            raise DRFValidationError(
                {"detail": "사용자 이메일 인증 정보가 누락되었습니다."},
            )

        # 3. code 유효 시간 체크
        if email_info.email_code_date is None:
            # 원하는 응답 구조를 'detail' 인자로 직접 전달합니다.
            raise DRFValidationError(
                 {"detail": "사용자 이메일 인증 정보가 누락되었습니다."},
            )
        if (timezone.now() - email_info.email_code_date) > timedelta(minutes=5):
            # 원하는 응답 구조를 'detail' 인자로 직접 전달합니다.
            raise DRFValidationError(
                {
                    "detail": "CODE 유효 시간이 지났습니다.(5분)"
                }
            )

        # 3. 이미 인증이 완료되었는지 확인
        # if email_info.email_auth:
        #     raise DRFValidationError(
        #         {"detail": _("이미 이메일 인증이 완료된 계정입니다.")},
        #         code='already_verified'
        #     )
        # 4. 인증 코드 일치 여부 확인 (수정된 부분)
        if not email_info.email_auth_code or email_info.email_auth_code != auth_code:
            # === 이 부분을 DRFValidationError를 사용하여 detail 응답으로 변경 ===
            raise DRFValidationError(
                {"detail": "인증 코드가 일치하지 않습니다. 다시 확인해 주세요."},
            )

        # TODO: 여기에 코드 유효 기간 확인 로직을 추가할 수 있습니다.

        # 유효성 검사를 통과한 UserEmail 객체를 context에 저장하여 view에서 사용
        self.context['email_info'] = email_info

        return data


# ----------------------------------------------------------------------
# 7. 이메일 변경 요청
#
# 참고. 이메일 인증 잠김 상태는 체크 하지 않는다.(잘 못된 이메일이 적용된 경우)
#
# ----------------------------------------------------------------------
MAX_ATTEMPTS = 3 # 최대 요청 횟수 (4회 초과 시 잠금)
LOCK_DURATION = 5 # 잠금 시간 (분)

def generate_verification_code():
    return ''.join(random.choices('0123456789', k=6))

class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(max_length=100)

    @transaction.atomic # 잠금 해제와 횟수 초기화 시 DB 반영을 위해 @transaction.atomic을 validate에 적용합니다.
    def validate(self, data):
        user = self.context['request'].user
        email_info = user.email_info # UserEmail 인스턴스
        new_email = data.get('new_email')

        # 1. 🛑 잠금 상태 확인 및 처리 (새로 추가된 핵심 로직)
        if email_info.email_reauth_lock:
            lock_time = email_info.email_reauth_date
            # 잠금 해제 예상 시간 = 잠금 시간 + 5분
            unlock_time = lock_time + timedelta(minutes=LOCK_DURATION)

            if timezone.now() < unlock_time:
                # 아직 잠금 시간이 지나지 않았음
                remaining_seconds = (unlock_time - timezone.now()).total_seconds()
                remaining_minutes = int(remaining_seconds // 60)

                # 잠금 상태이므로 요청 거부
                raise DRFValidationError({
                    "detail": f"이메일 변경 요청 횟수를 초과했습니다. 잠금 해제까지 약 {remaining_minutes + 1}분 남았습니다."
                })
            else:
                # 5분이 지났으므로 잠금 해제 및 횟수 초기화
                email_info.email_reauth_lock = False
                email_info.email_reauth_count = 0
                email_info.email_reauth_date = None
                # DB에 반영 (잠금 해제 후 다음 유효성 검사를 진행해야 하므로 미리 저장)
                email_info.save(update_fields=[
                    'email_reauth_lock', 'email_reauth_count', 'email_reauth_date'
                ])


        # --- 기존 유효성 검사 로직 ---
        # 1. 새 이메일이 기존 이메일과 같은지 확인
        if new_email == user.email:
            raise DRFValidationError({"detail": "기존 이메일 주소와 동일합니다."})

        # 2. 새 이메일이 이미 다른 계정의 최종 이메일로 사용 중인지 확인
        if UserInfo.objects.filter(email=new_email).exists():
            raise DRFValidationError({"detail": "사용 불가 이메일 주소입니다."})

        # 3. 새 이메일이 현재 다른 계정의 변경 대기 이메일로 사용 중인지 확인
        if UserInfo.objects.filter(new_email=new_email).exclude(pk=user.pk).exists():
            raise DRFValidationError({"detail": "현재 다른 사용자가 변경 요청 중인 이메일 주소입니다."})

        return data

    @transaction.atomic
    def save(self, **kwargs):
        user = self.context['request'].user
        new_email = self.validated_data['new_email']
        email_info = user.email_info # UserEmail 인스턴스 (Related Name: email_info)
        auth_code = generate_verification_code() # 인증 코드 생성

        # 1. UserInfo: 새로운 이메일을 임시 필드에 저장
        user.new_email = new_email
        user.save(update_fields=['new_email'])

        # 2. UserEmail: 재인증 횟수 확인 및 잠금 (횟수가 4회 이상이면 잠금)
        email_info.email_reauth_count += 1

        if email_info.email_reauth_count > MAX_ATTEMPTS:
            # 💥 4회 초과 시 잠금 설정
            email_info.email_reauth_lock = True
            email_info.email_reauth_date = timezone.now()
            email_info.save(update_fields=['email_reauth_lock', 'email_reauth_date', 'email_reauth_count'])

            # 잠금이 설정되었으므로, 이메일 발송 없이 에러를 발생시키기 위해
            # 여기서 예외를 발생시키거나, View에서 처리해야 합니다.
            # Serializer의 save()에서는 일반적으로 예외를 발생시키지 않으므로,
            # 이 로직은 validate()로 이동하는 것이 더 자연스럽습니다.
            # ❗ NOTE: 이 로직은 `validate()`로 이동했으므로, 여기서는 횟수 증가만 수행합니다.

        # 3. 코드 업데이트 및 저장 (인증 성공 또는 잠금 해제 후 다음 요청 시)
        email_info.email_auth_code = auth_code
        email_info.email_code_date = timezone.now()
        email_info.save(update_fields=['email_reauth_count', 'email_auth_code', 'email_code_date'])

        # 4. 이메일 전송
        send_auth_email_task.delay(new_email, auth_code) # 실제 함수 호출

        return user


# ----------------------------------------------------------------------
# 8. 이메일 변경 요청 인증
# ----------------------------------------------------------------------
class EmailChangeVerifySerializer(serializers.Serializer):
    #new_email = serializers.EmailField(max_length=100)
    code = serializers.CharField(max_length=10) # UserEmail.email_auth_code max_length에 맞춤

    @transaction.atomic # 잠금 상태 변경, 횟수 증가 및 DB 반영을 원자적으로 처리
    def validate(self, data):
        user = self.context['request'].user
        user_email_info = user.email_info

        #new_email_input = data.get('new_email')
        code_input = data.get('code')
        requested_email = user.new_email

        # 1. 🛑 잠금 상태 확인 및 처리 (요청 시 잠금 로직과 유사)
        if user_email_info.email_reauth_lock:
            lock_time = user_email_info.email_reauth_date
            unlock_time = lock_time + timedelta(minutes=LOCK_DURATION)

            if timezone.now() < unlock_time:
                remaining_seconds = (unlock_time - timezone.now()).total_seconds()
                remaining_minutes = int(remaining_seconds // 60)
                raise DRFValidationError({
                    "detail": f"이메일 재인증 시도 횟수를 초과했습니다. 잠금 해제까지 약 {remaining_minutes + 1}분 남았습니다."
                })
            else:
                # 5분이 지났으므로 잠금 해제 및 횟수 초기화
                user_email_info.email_reauth_lock = False
                user_email_info.email_reauth_count = 0
                user_email_info.email_reauth_date = None
                user_email_info.save(update_fields=[
                    'email_reauth_lock', 'email_reauth_count', 'email_reauth_date'
                ])

        # 2. 요청된 이메일 일치 확인
        # if user.new_email is None or user.new_email != new_email_input:
        #     raise DRFValidationError({"new_email": "변경 요청 중인 이메일 주소가 아니거나 요청이 진행 중이지 않습니다."})

        # 3. 인증 코드 일치 확인 및 횟수/잠금 로직 (인증 실패 시)
        if user_email_info.email_auth_code != code_input:

            # ❗ 인증 실패 시, 횟수 증가 및 잠금 처리
            user_email_info.email_reauth_count += 1

            if user_email_info.email_reauth_count > MAX_ATTEMPTS:
                # 잠금 (Lock) 실행
                user_email_info.email_reauth_lock = True
                user_email_info.email_reauth_date = timezone.now()
                user_email_info.save(update_fields=[
                    'email_reauth_count', 'email_reauth_lock', 'email_reauth_date'
                ])
                raise DRFValidationError({
                    "code": f"인증 코드가 {MAX_ATTEMPTS}회 이상 잘못 입력되어 계정이 {LOCK_DURATION}분 동안 잠금 처리됩니다."
                })
            else:
                # 횟수만 증가
                user_email_info.save(update_fields=['email_reauth_count'])
                raise DRFValidationError({
                    "code": f"인증 코드가 일치하지 않습니다. 남은 시도 횟수: {MAX_ATTEMPTS - user_email_info.email_reauth_count}"
                })

        # 4. 인증 코드 유효 기간 확인 (코드 일치 및 잠금 통과 시 체크)
        code_age = timezone.now() - user_email_info.email_code_date
        if code_age.total_seconds() > 300: # 300초 = 5분이라고 가정
             raise DRFValidationError({"code": "인증 코드가 만료되었습니다. 다시 요청해 주세요."})

        # 모든 유효성 검사 통과
        return data

    @transaction.atomic
    def save(self):
        user = self.context['request'].user
        user_email_info = user.email_info

        # 1. 이메일 업데이트 (Core Logic)
        user.email = user.new_email

        # 2. UserEmail 초기화 구조: 성공했으므로 모든 상태 초기화
        user_email_info.email_auth = True # 이메일 변경 완료
        user_email_info.email_auth_date = timezone.now().date()

        # 👇 초기화 (재인증 상태로 만들기)
        user_email_info.email_auth_count = 0
        user_email_info.email_auth_code = None
        user_email_info.email_code_date = None
        user_email_info.email_refresh_count = 0
        user_email_info.email_auth_lock = False
        user_email_info.email_lock_time = None
        user_email_info.email_reauth_count = 0
        user_email_info.email_reauth_lock = False
        user_email_info.email_reauth_date = None

        user_email_info.save()

        # 3. 임시 필드 초기화 및 UserInfo 업데이트
        user.new_email = None
        user.save(update_fields=['email', 'new_email'])

        # 4. (선택 사항) JWT 토큰 무효화 로직 추가...

        return user