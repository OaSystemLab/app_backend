import random

from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.contrib.auth import login
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from datetime import timedelta

from .models import UserGroup, UserInfo

# mail 처리 부분
from django.core.mail import send_mail
from django.conf import settings

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .tasks import send_auth_email_task # Celery Task import

from .utils.services import GroupService

# **하나의 import 문으로 필요한 모든 Serializer를 가져옵니다.**
from .serializers import (
    UserRegistrationSerializer,
    EmailAuthSendSerializer,
    EmailAuthConfirmSerializer,
    EmailChangeVerifySerializer,
    EmailChangeRequestSerializer,
    CustomTokenObtainPairSerializer,
    UserLoginSerializer,
    UserInfoListSerializer,
    UserInfoNicknameUpdateSerializer,
    MasterTransferSerializer,
    MemberKickSerializer,
)

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

# ----------------------------------------------------------------------
# UserList ViewSet (가족 리스트 가져 오기 )
# ----------------------------------------------------------------------
class UserInfoListAPIView(APIView):
    """
    현재 인증된 사용자 (UserInfo) 의 가족 그룹(family_group_id) 내용 가져오기
    URL: /user_list/
    """
    # 📌 이 뷰는 로그인된 사용자만 접근 가능하도록 Permission 설정을 추가해야 합니다.
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. 현재 요청을 보낸 사용자 (UserInfo) 객체 가져오기
        user = request.user

        # 2. 사용자 객체에서 CharField인 family_group_id 값 가져오기
        family_group_id = user.family_group_id

        # 3. family_group_id 값이 없는지 확인
        if not family_group_id:
            return Response(
                {"detail": "가족 그룹이 없습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. UserGroup 객체 조회 (요청하신 filter() 구조 사용)
        family_group_qs = UserGroup.objects.filter(family_group_id=family_group_id)

        # 5. 조회된 UserGroup이 없는 경우 처리
        if not family_group_qs.exists():
             return Response(
                {"detail": f"ID '{family_group_id}'에 해당하는 가족 그룹이 존재하지 않습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 6. UserGroup QuerySet을 사용하여 연결된 user_info 객체들 가져오기
        # 연결된 UserInfo의 Primary Key (ID) 리스트 추출
        user_info_pks = family_group_qs.values_list('user__pk', flat=True).distinct()

        # UserInfo 모델에서 해당 PK를 가진 모든 객체를 조회
        user_info_list = UserInfo.objects.filter(pk__in=user_info_pks)

        # 7. 시리얼라이즈 및 응답
        # 여러 객체를 시리얼라이즈하므로 반드시 many=True 옵션을 사용합니다.
        serializer = UserInfoListSerializer(user_info_list, many=True)

        # 결과는 JSON 배열 형태로 반환됩니다.
        return Response(serializer.data, status=status.HTTP_200_OK)

# ----------------------------------------------------------------------
# UserInfo Nick Name Edit....
# ----------------------------------------------------------------------
class UserInfoNickNameUpdateAPIView(APIView):
    """
    UserInfo Nick Name 수정하는 API.
    """
    # 📌 권한 설정: 로그인된 사용자만 접근 허용
    permission_classes = [IsAuthenticated]

    # {
    #     "new_nick_name": "거실"
    # }

    def post(self, request, *args, **kwargs):

        user = request.user

        # 2. 시리얼라이저를 사용하여 요청 데이터 검증
        serializer = UserInfoNicknameUpdateSerializer(data=request.data)

        # 데이터 유효성 검사 실패 시 400 Bad Request 응답
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 3. 검증된 데이터 추출
        new_nick_name = serializer.validated_data['nick_name']

        # 4. Nick Name 업데이트
        user.nick_name = new_nick_name
        user.save()

        # 5. 성공 응답 반환
        return Response(
            {
                "detail": "닉 네임이 성공적으로 수정되었습니다."
            },
            status=status.HTTP_200_OK
        )
# ----------------------------------------------------------------------
# 마스터 변경
# ----------------------------------------------------------------------
# {
#     "new_master_user_id" :1234
# }
class MasterTransferView(APIView):
    """가족 그룹 마스터 권한을 다른 사용자에게 이양하는 API 엔드포인트"""
    permission_classes = [IsAuthenticated] # 로그인 필수

    def post(self, request, *args, **kwargs):
        serializer = MasterTransferSerializer(data=request.data)
        # 데이터 유효성 검사 실패 시 자동적으로 HTTP 400 응답 반환
        serializer.is_valid(raise_exception=True)

        new_master_user_id = serializer.validated_data['new_master_user_id']
        current_master_user_id = request.user.id # 로그인된 사용자 (현재 마스터)의 ID

        try:
            success, message = GroupService.transfer_master_authority_with_group_id_change(
                current_master_user_id=current_master_user_id,
                new_master_user_id=new_master_user_id
            )

            if success:
                return Response(
                    {"detail": message},
                    status=status.HTTP_200_OK
                )
            else:
                # 서비스에서 발생한 오류 메시지를 그대로 반환
                return Response(
                    {"detail": message},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except (PermissionDenied, ValidationError) as e:
            # 서비스 계층이 아닌 뷰 계층에서 예외를 처리해야 할 경우를 대비
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
# ----------------------------------------------------------------------
# 가족 그룹 탈퇴
# DELETE
# ----------------------------------------------------------------------
class FamilyGroupLeaveView(APIView):
    """
    가족 그룹 탈퇴를 처리하는 API 엔드포인트
    DELETE 요청을 통해 탈퇴를 실행합니다.
    """
    permission_classes = [IsAuthenticated] # 로그인 필수

    def delete(self, request, *args, **kwargs):
        current_user_id = request.user.id # 로그인된 사용자 ID

        success, message = GroupService.leave_family_group(
            user_id=current_user_id
        )

        if success:
            return Response(
                {"detail": message},
                status=status.HTTP_200_OK
            )
        else:
            # 403 FORBIDDEN: 마스터 권한으로 인해 탈퇴가 거부됨
            if "마스터입니다" in message:
                return Response(
                    {"detail": message},
                    status=status.HTTP_403_FORBIDDEN
                )
            # 400 BAD REQUEST: 기타 유효성 또는 시스템 오류
            return Response(
                {"detail": message},
                status=status.HTTP_400_BAD_REQUEST
            )
# ----------------------------------------------------------------------
# 가족 그룹 추방
# POST
# {
#     "target_user_id": 456
# }
# ----------------------------------------------------------------------
class FamilyGroupKickView(APIView):
    """
    마스터가 특정 멤버를 가족 그룹에서 추방하는 API 엔드포인트
    """
    permission_classes = [IsAuthenticated] # 로그인 필수

    def post(self, request, *args, **kwargs):
        serializer = MemberKickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_user_id = serializer.validated_data['target_user_id']
        master_user_id = request.user.id # 로그인된 사용자 (마스터)의 ID

        success, message = GroupService.kick_member_from_group(
            master_user_id=master_user_id,
            target_user_id=target_user_id
        )

        if success:
            return Response(
                {"detail": message},
                status=status.HTTP_200_OK
            )
        else:
            # 403 FORBIDDEN: 권한 없음 (마스터가 아님)
            if "권한이 없습니다" in message:
                return Response(
                    {"detail": message},
                    status=status.HTTP_403_FORBIDDEN
                )
            # 400 BAD REQUEST: 기타 유효성 오류 (그룹 불일치, 자기 자신 추방 시도 등)
            return Response(
                {"detail": message},
                status=status.HTTP_400_BAD_REQUEST
            )