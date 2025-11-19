import random

from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import OasGroup
from .serializers import UserRegistrationSerializer, UserLoginSerializer, OasGroupSerializer, EmailAuthSendSerializer, EmailAuthConfirmSerializer, EmailChangeRequestSerializer, EmailChangeVerifySerializer
from django.contrib.auth import login
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

# mail 처리 부분
from django.core.mail import send_mail
from django.conf import settings

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication # settings.py에 설정된 인증 클래스와 일치해야 합니다.
from .serializers import CustomTokenObtainPairSerializer

from .tasks import send_auth_email_task # Celery Task import

# ----------------------------------------------------------------------
# 1. 사용자 등록 View
# ----------------------------------------------------------------------
class UserRegistrationView(generics.CreateAPIView):
    """
    사용자 등록 (회원가입)을 처리하는 API View
    """
    serializer_class = UserRegistrationSerializer
    # 모든 사용자가 접근 가능하도록 설정
    permission_classes = [permissions.AllowAny]


# ----------------------------------------------------------------------
# 2. 사용자 로그인 View (추가)
# ----------------------------------------------------------------------
class UserLoginView(APIView):
    """
    사용자 로그인 및 세션(또는 토큰) 발급을 처리하는 API View
    """
    serializer_class = UserLoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, format=None):
        serializer = self.serializer_class(data=request.data, context={'request': request})

        if serializer.is_valid(raise_exception=True):
            user = serializer.validated_data['user']
            # Django 세션 기반 로그인 (필요에 따라 주석 처리 가능)
            # login(request, user)

            # TODO: 실제 프로덕션 환경에서는 JWT 토큰 생성 및 반환 로직이 여기에 추가됩니다.

            return Response({
                'message': 'Login successful.',
                'email': user.email,
                'nick_name': user.nick_name,
                # 'token': 'JWT_TOKEN_HERE' # JWT 토큰을 반환하는 것이 일반적
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ----------------------------------------------------------------------
# 3. api/token 이용한 로그인시 전달 해 줄 정보
# ----------------------------------------------------------------------
class CustomTokenObtainPairView(TokenObtainPairView):
    # 커스텀 Serializer를 연결합니다.
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]

# ----------------------------------------------------------------------
# 4. 임시 2025.10.27 View (삭제 필요...)
# ----------------------------------------------------------------------
class OasGroupListAPIView(generics.ListAPIView):
    # 어떤 모델 객체를 가져올지 지정합니다 (전체 객체)
    queryset = OasGroup.objects.all()

    # 가져온 객체를 어떤 Serializer로 변환할지 지정합니다
    serializer_class = OasGroupSerializer

    # 참고: 만약 특정 조건의 리스트만 보고 싶다면 get_queryset 메서드를 오버라이드합니다.
    # def get_queryset(self):
    #     return OasGroup.objects.filter(some_field='value')


# ----------------------------------------------------------------------
# 5. email 인증 코드 보내기
# ----------------------------------------------------------------------
# 임시 이메일 전송 함수 (실제로는 SMTP 설정이 필요합니다)
def send_auth_email(email, code):
    """실제 이메일 전송 로직이 들어갈 자리입니다."""
    print(f"📧 이메일 전송 시뮬레이션: {email}에게 인증 코드 {code} 전송됨.")

    subject = "회원가입 이메일 인증 코드"
    message = f"인증 코드는 {code} 입니다. 5분 내에 입력해 주세요."
    html_message_template = """
    <html>
    <body>
        <h3 >이메일 인증</h3>

        <p>
            ℹ️ 인증번호 6자리 <strong>{code}</strong>
        <br>
        <p>
            위 6자리 번호를 입력하여 인증을 완료하세요.<br>
            <br>
            <strong>인증번호는 5분간 유효합니다.</strong>
        </p>
    </body>
    </html>
    """
    html_message = html_message_template.format(code=code)
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [email]


    try:
        send_mail(
            subject,
            message,
            from_email,
            recipient_list,
            fail_silently=False, # 전송 실패 시 예외 발생
            html_message=html_message,
        )
        return "이메일 전송 성공"
    except Exception as e:
        # 전송 실패 시 처리
        print(f"이메일 전송 실패: {e}")
        return "이메일 전송 실패"

class EmailAuthSendView(APIView):
    """
    이메일로 인증 코드를 전송하고, UserEmail 모델의 상태를 업데이트합니다.
    (잠금 해제, 카운트 증가, 신규 잠금 등)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated] # IsAuthenticated로 수정 권장

    @transaction.atomic # DB 업데이트와 이메일 전송 요청을 원자적으로 처리
    def post(self, request):
        user = request.user
        # Serializer에 요청 객체를 context로 전달하여 Serializer 내부에서 user 정보를 사용하도록 합니다.
        serializer = EmailAuthSendSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        # 1. 유효성 검사
        # Serializer는 이제 5분 미만 잠금 상태일 때만 오류를 발생시킴
        serializer.is_valid(raise_exception=True)

        # 2. 필요 데이터 준비
        email = user.email
        email_info = serializer.context['email_info']

        if not email_info:
            # 이 코드가 실행되면, Serializer가 유효성 검사를 통과했음에도
            # email_info를 context에 저장하지 못했다는 뜻입니다.
            # 이는 Serializer 내부에 치명적인 버그가 있거나,
            # UserEmail.DoesNotExist 예외 처리가 잘못된 경우입니다.
            return Response({
                "detail": "인증 정보 객체를 찾을 수 없습니다. (내부 오류)",
                "code": "ERROR_NO_EMAIL_INFO"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


        auth_code = ''.join(random.choices('0123456789', k=6))

        response_message = "인증 코드가 이메일로 전송되었습니다. 코드를 확인해 주세요."
        response_code = "RE000"

        # 3. 비즈니스 로직 처리 (DB 상태 변경)
        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is True and email_info.email_lock_time is None :
            print("이슈 email_refresh_count > 3, email_auth_lock is True,email_lock_time is None ")
            email_info.email_auth_lock = False
            email_info.email_lock_time = None
            email_info.email_refresh_count = 1 # 1로 초기화


        if email_info.email_refresh_count > 3 and email_info.email_auth_lock is False and email_info.email_lock_time is not None :
            print("이슈 email_refresh_count > 3, email_auth_lock is False,email_lock_time is not None ")
            email_info.email_lock_time = None
            email_info.email_refresh_count = 1 # 1로 초기화

        if email_info.email_refresh_count > 3 and  email_info.email_auth_lock is False and email_info.email_lock_time is None :
            print("이슈 email_refresh_count > 3, email_auth_lock is False,email_lock_time is None ")
            email_info.email_lock_time = None
            email_info.email_refresh_count = 1 # 1로 초기화


        # [A] 잠금 상태였으나 5분이 경과하여 잠금을 해제하고 카운트를 리셋하는 경우
        if email_info.email_auth_lock:
            # Serializer가 5분 미만은 걸러냈으므로, 이 로직은 5분이 지났다는 의미
            print("5분이 경과하여 잠금을 해제하고 카운트를 1로 초기화합니다.")
            email_info.email_auth_lock = False
            email_info.email_lock_time = None
            email_info.email_refresh_count = 1 # 1로 초기화

        # [B] 잠금 상태가 아니었으며, 카운트를 증가시키는 경우
        else:
            email_info.email_refresh_count += 1
            print(f"카운트를 1 증가시킵니다. 현재: {email_info.email_refresh_count}")

            # [C] 카운트 증가 결과, 4회 이상이 되어 잠금이 *새로* 설정되는 경우
            if email_info.email_refresh_count > 3:
                print("카운트가 4회가 되어 계정을 잠급니다.")
                email_info.email_auth_lock = True
                email_info.email_lock_time = timezone.now()
                print("timezone.now() : ", timezone.now())
                response_message = "코드가 전송되었습니다. 하지만 4회 이상 요청으로 5분간 계정이 잠깁니다."
                response_code = "RE003" # 잠금 알림 코드

        # [D] 공통 작업: 인증 코드 및 시간 업데이트
        email_info.email_auth_code = auth_code
        email_info.email_code_date = timezone.now()
        email_info.save()

        # 4. 이메일 전송 (비동기)
        send_auth_email_task.delay(email, auth_code) # 실제 운영 시 주석 해제
        print(f"비동기 이메일 전송 요청: {email}로 {auth_code} 전송") # 테스트용 로그

        # 5. 응답 반환
        return Response({
            "detail": [ response_message ],
            #"code": response_code
        }, status=status.HTTP_200_OK)

# ----------------------------------------------------------------------
# 5. email 인증 코드 검증
#
# 표준 DRF 동작 원리 설명
# DRF에서 Serializer의 is_valid(raise_exception=True)를 호출하면 다음과 같이 작동합니다:
#
# 1. is_valid() 호출 → validate() 메서드 실행.
# 2. validate() 메서드 내에서 유효성 검사 실패 시 ValidationError (혹은 DRFValidationError)를 raise 합니다.
# 3. raise_exception=True 옵션 덕분에, 이 예외는 DRF의 예외 핸들러에 의해 자동으로 잡히고,
#    표준 에러 응답 형식(보통 HTTP 400 Bad Request와 JSON 형식의 에러 메시지)으로 클라이언트에게 반환됩니다.
#
# ----------------------------------------------------------------------
class EmailAuthConfirmView(APIView):
    """
    이메일로 받은 인증 코드를 확인하고, 인증이 성공하면 계정의 email_auth 상태를 True로 변경합니다.
    """

    # 1. 인증 클래스 지정: JWT 토큰을 사용하여 사용자를 인증합니다.
    authentication_classes = [JWTAuthentication]
    # 2. 권한 클래스 지정: 인증된 사용자만 접근을 허용합니다.
    permission_classes = [IsAuthenticated]

    @transaction.atomic # DB 업데이트를 원자적으로 처리
    def post(self, request):
        # request.user는 JWT 토큰을 통해 인증된 UserInfo 인스턴스입니다.
        user = request.user

        # Serializer에 요청 객체를 context로 전달하여 Serializer 내부에서 user 정보를 사용하도록 합니다.
        serializer = EmailAuthConfirmSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        email_info = serializer.context['email_info'] # Serializer에서 가져옴


        # 1. UserEmail 객체의 상태 업데이트
        email_info.email_auth = True
        email_info.email_auth_code = None # 인증 완료 후 코드 제거 (재사용 방지)
        email_info.email_code_date = None # 인증 완료 후 코드 제거 (재사용 방지)
        email_info.email_auth_date = timezone.now().date()
        # 기타 인증 관련 카운트/락 필드 초기화 (선택 사항)
        email_info.email_auth_count += 1
        email_info.email_refreash_count = 0
        email_info.email_auth_lock = False
        email_info.email_lock_time = None
        email_info.save()

        return Response({
            "detail": ("이메일 인증이 성공적으로 완료되었습니다."),
            "email": user.email,
            "email_auth": True
        }, status=status.HTTP_200_OK)


# ----------------------------------------------------------------------
# 6. email 변경 요청
# ----------------------------------------------------------------------
class EmailChangeRequestView(APIView):
    """새 이메일 주소를 제출하고 인증 코드를 요청합니다."""

    # JWTAuthentication을 사용하신다면 그대로 두시면 됩니다.
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request): # @transaction.atomic은 Serializer.save()로 이동 권장
        serializer = EmailChangeRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        # Serializer의 save() 메서드가 DB 저장 및 이메일 발송 로직을 모두 처리합니다.
        serializer.save()

        return Response(
            {"detail": "새 이메일로 인증 코드가 발송되었습니다. 코드를 확인해 주세요."},
            status=status.HTTP_200_OK
        )

# ----------------------------------------------------------------------
# 7. 이메일 변경 확인 (Verify) View
# ----------------------------------------------------------------------
class EmailChangeVerifyView(APIView):
    """
    인증 코드를 제출하여 이메일 주소 변경을 완료합니다.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EmailChangeVerifySerializer(
            data=request.data,
            context={'request': request}
        )
        # validate 메서드에서 잠금/횟수 처리 및 인증 코드 일치 확인 후 예외 발생
        serializer.is_valid(raise_exception=True)

        # save 메서드에서 최종 이메일 업데이트 및 UserEmail 초기화가 이루어짐
        serializer.save()

        # 이메일 변경 후 재로그인을 유도하는 메시지 반환
        return Response(
            {"detail": "이메일 주소 변경이 성공적으로 완료되었습니다. 새 이메일로 다시 로그인해 주세요."},
            status=status.HTTP_200_OK
        )