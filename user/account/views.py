import random

from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import OasGroup
from .serializers import UserRegistrationSerializer, UserLoginSerializer, OasGroupSerializer, EmailAuthSendSerializer, EmailAuthConfirmSerializer
from django.contrib.auth import login
from django.db import transaction
from django.utils import timezone

# mail 처리 부분
from django.core.mail import send_mail
from django.conf import settings

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication # settings.py에 설정된 인증 클래스와 일치해야 합니다.
from .serializers import CustomTokenObtainPairSerializer

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
    이메일로 인증 코드를 전송하고, UserEmail 모델을 업데이트합니다.
    """
    # 인증이 필요 없는 API입니다 (로그인 전에 사용).
    # permission_classes = [permissions.AllowAny] # 필요에 따라 추가

    # 1. 인증 클래스 지정: JWT 토큰을 사용하여 사용자를 인증합니다.
    authentication_classes = [JWTAuthentication]
    # 2. 권한 클래스 지정: 인증된 사용자만 접근을 허용합니다.
    permission_classes = [IsAuthenticated]

    @transaction.atomic # DB 업데이트와 이메일 전송을 원자적으로 처리
    def post(self, request):
        # request.user는 JWT 토큰을 통해 인증된 UserInfo 인스턴스입니다.
        user = request.user

        # Serializer에 요청 객체를 context로 전달하여 Serializer 내부에서 user 정보를 사용하도록 합니다.
        serializer = EmailAuthSendSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        # 유효성 검사를 통과했으므로, 이메일 주소와 email_info 객체를 사용자 인스턴스에서 가져옵니다.
        email = user.email
        email_info = serializer.context['email_info'] # Serializer에서 가져옴

        # 1. 6자리 랜덤 인증 코드 생성
        auth_code = ''.join(random.choices('0123456789', k=6))

        # 2. UserEmail 모델 필드 업데이트 및 카운트 증가 로직 (미리 정의된 필드 활용)
        email_info.email_auth_code = auth_code
        #email_info.email_auth_count += 1      # 인증 시도 횟수 증가
        email_info.email_refresh_count += 1   # 다시 전송 횟수 증가
        #email_info.email_auth_date = timezone.now().date() # 인증 시도 날짜 기록

        # TODO: 여기에 재전송 횟수/인증 횟수 제한 로직을 추가해야 합니다.
        # 예: if email_info.email_auth_count > 5: email_info.email_auth_lock = True

        email_info.save()

        # 3. 인증 이메일 전송 (실제 SMTP 설정 필요)
        send_auth_email(email, auth_code)

        return Response({
            "message": "인증 코드가 이메일로 전송되었습니다. 코드를 확인해 주세요.",
            "email": email,
            #"send_count": email_info.email_refresh_count
        }, status=status.HTTP_200_OK)

# ----------------------------------------------------------------------
# 5. email 인증 코드 검증
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
        email_info.email_auth_date = timezone.now().date()
        # 기타 인증 관련 카운트/락 필드 초기화 (선택 사항)
        email_info.email_auth_count += 1
        email_info.email_refreash_count = 0
        email_info.email_auth_lock = False
        email_info.email_lock_time = None
        email_info.save()

        return Response({
            "message": ("이메일 인증이 성공적으로 완료되었습니다."),
            "email": user.email,
            "email_auth": True
        }, status=status.HTTP_200_OK)