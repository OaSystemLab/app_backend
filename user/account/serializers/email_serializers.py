from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
import random
from ..tasks import send_auth_email_task # Celery Task import

# .models는 상위 디렉토리의 models.py를 참조하도록 수정 필요
# 앱 구조에 따라 .models를 사용하거나, 절대 경로 import를 사용해야 합니다.
from ..models import UserInfo, UserEmail # 🚨 앱 구조에 따라 수정해야 할 수 있음!


MAX_ATTEMPTS = 3 # 최대 요청 횟수 (4회 초과 시 잠금)
LOCK_DURATION = 5 # 잠금 시간 (분)

def generate_verification_code():
    return ''.join(random.choices('0123456789', k=6))

# ----------------------------------------------------------------------
# 5. email 인증 코드 요청 하기 전에 검증 하는 부분
# ----------------------------------------------------------------------
class EmailAuthSendSerializer(serializers.Serializer):
    """ 로그인된 사용자의 정보를 사용하여 이메일 인증 코드를 전송하기 위한 Serializer입니다. """

    # ... (기존의 validate 로직은 그대로 유지) ...
    def validate(self, data):
        # View에서 self.request.user를 context로 넘겨받는다고 가정합니다.
        request = self.context.get('request')

        if not request:
            raise DRFValidationError("요청 객체를 context에서 찾을 수 없습니다. View 설정을 확인하세요.")

        user = request.user

        # 1. 사용자 객체 인증 여부 확인
        if not user.is_authenticated:
            raise DRFValidationError(
                {"detail": "요청을 처리하려면 유효한 로그인 토큰이 필요합니다."},
                code='not_authenticated'
            )

        # 2. UserEmail 객체 조회
        try:
            email_info = user.email_info
        except Exception:
            raise DRFValidationError(
                {"detail": "계정에 연결된 인증 정보가 누락되었습니다. 관리자에게 문의해 주세요."},
                code='missing_email_info'
            )

        # 버그성 이슈 처리 (버그 수정은 별도로 고려해야 하나, 현재 로직은 유지)
        # 예외 상황 발생
        # 이슈. email_auth_lock 값이 있으나 email_lock_time 없는 경우 발생
        #      위 같은 상황이면 계속 해서 잠김 상태로 가게 됨.
        # TODO.  email_auth_lock, email_lock_time 둘 중에 하나만 있는경우 처리 방안은?
        #        email_auth_lock True email_lock_time None 경우는 email_auth_lock 해제 하고 처음 부터 하게함
        #        email_auth_lock False email_lock_time 있는 경우는 email_lock_time 초기화
        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is True and email_info.email_lock_time is None :
             print("버그 이슈 email_refresh_count > 3 , email_auth_lock is True,email_lock_time is None ")
             self.context['email_info'] = email_info
             return data

        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is False and email_info.email_lock_time is not None :
             print("버그 이슈 email_refresh_count > 3, email_auth_lock is False,email_lock_time is not None ")
             self.context['email_info'] = email_info
             return data

        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is False and email_info.email_lock_time is None :
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

        self.context['email_info'] = email_info

        return data

# ----------------------------------------------------------------------
# 6. 인증 메일서 받은 코드 검증 하기 전에 체크 하는 부분
# ----------------------------------------------------------------------
class EmailAuthConfirmSerializer(serializers.Serializer):
    """ 사용자로부터 받은 이메일과 인증 코드를 검증하고, 인증이 완료되면 UserEmail 모델의 상태를 업데이트할 준비를 합니다. """

    auth_code = serializers.CharField(
        max_length=10,
        required=True,
        label=_("인증 코드")
    )

    # ... (기존의 validate 로직은 그대로 유지) ...
    def validate(self, data):
        user = self.context['request'].user
        auth_code = data.get('auth_code')

        # 1. 사용자 객체 인증 여부 확인
        if not user.is_authenticated:
            raise DRFValidationError({"detail": "로그인이 필요합니다."})
        # 2. UserEmail 객체 확인
        try:
            email_info = user.email_info
        except UserEmail.DoesNotExist:
            raise DRFValidationError({"detail": "사용자 이메일 인증 정보가 누락되었습니다."})

        # 3. code 유효 시간 체크
        if email_info.email_code_date is None:
            raise DRFValidationError({"detail": "사용자 이메일 인증 정보가 누락되었습니다."})
        if (timezone.now() - email_info.email_code_date) > timedelta(minutes=5):
            raise DRFValidationError({"detail": "CODE 유효 시간이 지났습니다.(5분)"})

        # 4. 인증 코드 일치 여부 확인
        if not email_info.email_auth_code or email_info.email_auth_code != auth_code:
            raise DRFValidationError({"detail": "인증 코드가 일치하지 않습니다. 다시 확인해 주세요."})

        self.context['email_info'] = email_info
        return data


# ----------------------------------------------------------------------
# 7. 이메일 변경 요청
# ----------------------------------------------------------------------
class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(max_length=100)

    @transaction.atomic
    def validate(self, data):
        user = self.context['request'].user
        email_info = user.email_info
        new_email = data.get('new_email')

        # 1. 🛑 잠금 상태 확인 및 처리
        if email_info.email_reauth_lock:
            lock_time = email_info.email_reauth_date
            unlock_time = lock_time + timedelta(minutes=LOCK_DURATION)

            if timezone.now() < unlock_time:
                remaining_seconds = (unlock_time - timezone.now()).total_seconds()
                remaining_minutes = int(remaining_seconds // 60)
                raise DRFValidationError({
                    "detail": f"이메일 변경 요청 횟수를 초과했습니다. 잠금 해제까지 약 {remaining_minutes + 1}분 남았습니다."
                })
            else:
                # 5분이 지났으므로 잠금 해제 및 횟수 초기화 (DB 반영)
                email_info.email_reauth_lock = False
                email_info.email_reauth_count = 0
                email_info.email_reauth_date = None
                email_info.save(update_fields=[
                    'email_reauth_lock', 'email_reauth_count', 'email_reauth_date'
                ])


        # --- 기존 유효성 검사 로직 ---
        if new_email == user.email:
            raise DRFValidationError({"detail": "기존 이메일 주소와 동일합니다."})

        if UserInfo.objects.filter(email=new_email).exists():
            raise DRFValidationError({"detail": "사용 불가 이메일 주소입니다."})

        if UserInfo.objects.filter(new_email=new_email).exclude(pk=user.pk).exists():
            raise DRFValidationError({"detail": "현재 다른 사용자가 변경 요청 중인 이메일 주소입니다."})

        return data

    @transaction.atomic
    def save(self, **kwargs):
        user = self.context['request'].user
        new_email = self.validated_data['new_email']
        email_info = user.email_info
        auth_code = generate_verification_code()

        # 1. UserInfo: 새로운 이메일을 임시 필드에 저장
        user.new_email = new_email
        user.save(update_fields=['new_email'])

        # 2. UserEmail: 재인증 횟수 확인 및 잠금 (validate()에서 잠금 해제 처리했으므로 여기서는 횟수 증가 및 잠금만)
        email_info.email_reauth_count += 1

        if email_info.email_reauth_count > MAX_ATTEMPTS:
            # 💥 4회 초과 시 잠금 설정
            email_info.email_reauth_lock = True
            email_info.email_reauth_date = timezone.now()
            # ❗ save() 로직을 View로 이동하는 것을 고려해 보세요.
            # Serializer의 save()는 객체 생성/업데이트 역할에 집중하는 것이 좋습니다.
            email_info.save(update_fields=['email_reauth_lock', 'email_reauth_date', 'email_reauth_count'])
            # ❗ validate()에서 이미 거부되었으므로 이 로직은 여기에 도달하지 않아야 합니다. (방어적 코딩)
            # 안전하게 처리하려면 여기서 예외를 발생시켜야 합니다.

        # 3. 코드 업데이트 및 저장
        email_info.email_auth_code = auth_code
        email_info.email_code_date = timezone.now()
        # ❗ 잠금 로직이 validate()에 있다면 여기서는 횟수 증가와 코드 업데이트만 반영
        email_info.save(update_fields=['email_reauth_count', 'email_auth_code', 'email_code_date'])


        # 4. 이메일 전송
        send_auth_email_task.delay(new_email, auth_code)

        return user


# ----------------------------------------------------------------------
# 8. 이메일 변경 요청 인증
# ----------------------------------------------------------------------
class EmailChangeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)

    @transaction.atomic
    def validate(self, data):
        user = self.context['request'].user
        user_email_info = user.email_info
        code_input = data.get('code')

        # 1. 🛑 잠금 상태 확인 및 처리
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

        # 2. 인증 코드 일치 확인 및 횟수/잠금 로직 (인증 실패 시)
        if user_email_info.email_auth_code != code_input:
            user_email_info.email_reauth_count += 1

            if user_email_info.email_reauth_count > MAX_ATTEMPTS:
                user_email_info.email_reauth_lock = True
                user_email_info.email_reauth_date = timezone.now()
                user_email_info.save(update_fields=[
                    'email_reauth_count', 'email_reauth_lock', 'email_reauth_date'
                ])
                raise DRFValidationError({
                    "code": f"인증 코드가 {MAX_ATTEMPTS}회 이상 잘못 입력되어 계정이 {LOCK_DURATION}분 동안 잠금 처리됩니다."
                })
            else:
                user_email_info.save(update_fields=['email_reauth_count'])
                raise DRFValidationError({
                    "code": f"인증 코드가 일치하지 않습니다. 남은 시도 횟수: {MAX_ATTEMPTS - user_email_info.email_reauth_count}"
                })

        # 3. 인증 코드 유효 기간 확인
        code_age = timezone.now() - user_email_info.email_code_date
        if code_age.total_seconds() > 300:
             raise DRFValidationError({"code": "인증 코드가 만료되었습니다. 다시 요청해 주세요."})

        return data

    @transaction.atomic
    def save(self):
        user = self.context['request'].user
        user_email_info = user.email_info

        # 1. 이메일 업데이트 (Core Logic)
        user.email = user.new_email

        # 2. UserEmail 초기화 및 UserInfo 업데이트
        user_email_info.email_auth = True
        user_email_info.email_auth_date = timezone.now().date()
        # 👇 초기화 필드들 (생략 없이 모두 유지)
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

        return user