# oas/auth/device/views.py


from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import OasGroup, OasInfo
from .serializers import OasGroupSerializer, OasInfoSerializer, AuthRequestSerializer
from rest_framework.permissions import IsAuthenticated

from .utils.crypto import decrypt_qr_data_cryptography
from .utils.remote_manager import Bootup

# 시간 비교를 위한 import
from datetime import datetime, timedelta
from django.utils import timezone

# ----------------------------------------------------------------------
# 1. OasGroup ViewSet (환경 제어기 그룹 관리)
# ----------------------------------------------------------------------
class OasGroupViewSet(viewsets.ModelViewSet):
    """
    OasGroup 모델에 대한 CRUD 작업을 제공하는 ViewSet입니다.
    기본적으로 모든 등록된 환경 제어기 그룹을 조회하고 관리할 수 있습니다.
    """
    # 이 ViewSet이 처리할 모델의 쿼리셋을 정의합니다.
    queryset = OasGroup.objects.all()

    # 이 ViewSet이 사용할 Serializer 클래스를 지정합니다.
    serializer_class = OasGroupSerializer

    # API 접근 권한 설정 (로그인된 사용자만 접근 가능하도록 가정)
    # 필요에 따라 다른 권한 설정으로 변경할 수 있습니다.
    permission_classes = [IsAuthenticated]


# ----------------------------------------------------------------------
# 2. OasInfo ViewSet (환경 제어기 상세 정보 관리)
# ----------------------------------------------------------------------
class OasInfoViewSet(viewsets.ModelViewSet):
    """
    OasInfo 모델에 대한 CRUD 작업을 제공하는 ViewSet입니다.
    환경 제어기의 상세 정보를 조회하고 관리할 수 있습니다.
    """
    # 이 ViewSet이 처리할 모델의 쿼리셋을 정의합니다.
    queryset = OasInfo.objects.all()

    # 이 ViewSet이 사용할 Serializer 클래스를 지정합니다.
    serializer_class = OasInfoSerializer

    # API 접근 권한 설정 (로그인된 사용자만 접근 가능하도록 가정)
    permission_classes = [IsAuthenticated]

# ----------------------------------------------------------------------
# 3. Auth API View (환경 제어기 인증 요청 처리)
# ----------------------------------------------------------------------
class AuthAPIView_old(APIView):
    """
    환경 제어기 인증 요청을 처리하는 API입니다.
    POST 요청만 허용하며, 인증된 사용자(IsAuthenticated)만 접근 가능합니다.
    """
    # ⭐️ 인증된 사용자만 접근 가능하도록 설정합니다.
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):

        decrypted_json = decrypt_qr_data_cryptography(request.data.get('data'))

        print("decrypted_json : " , decrypted_json)

        # 1. create sitecode
        device_check = {
            "dev_id" : decrypted_json['site'] +
                       decrypted_json['dong'] +
                       decrypted_json['ho']   +
                       decrypted_json['id'],
            "deviceId" : decrypted_json['deviceId']
        }
        # print("device_check : ", device_check)
        # 2. Remote Backend 검증 요청
        api_response_data = Bootup.check_request(device_check)

        if api_response_data.get('status') is False:
            return Response(
                {"detail": "등록 되지 않은 환경제어기가 입니다. 등록 후 사용 해주세요."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AuthRequestSerializer(data=decrypted_json, context={'request': request})

        print("api_response_data : " , api_response_data)


        # 1. Serializer를 통한 데이터 유효성 검사
        if serializer.is_valid():

            # 2. 인증 로직 처리 (TODO)
            # 현재는 데이터 검증까지만 수행합니다.
            # 여기에 실제 OasInfo 조회, 인증 카운트 증가, 상태 변경 등 핵심 로직이 들어갑니다.

            # 임시 응답 (성공)
            return Response(
                {"message": "인증 요청 데이터가 유효하며 처리 대기 중입니다.",
                 "data": serializer.validated_data},
                status=status.HTTP_200_OK
            )

        # 3. 데이터 유효성 검사 실패
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AuthAPIView(APIView):
    """
    환경 제어기 인증 요청을 처리하는 API입니다.
    POST 요청만 허용하며, 인증된 사용자(IsAuthenticated)만 접근 가능합니다.
    """
    # ⭐️ 인증된 사용자만 접근 가능하도록 설정합니다.
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. 암호화된 데이터 추출 및 복호화 시도
        encrypted_data = request.data.get('data')
        if not encrypted_data:
            return Response(
                {"detail": "'data' 필드가 누락되었습니다."},
                status=status.HTTP_400_BAD_REQUEST
        )

        decrypted_json = decrypt_qr_data_cryptography(encrypted_data)
        if decrypted_json is None:
            return Response(
                {"detail": "데이터가 유효하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST # 또는 HTTP_401_UNAUTHORIZED
            )

        # 2. QRCODE 시간 유효성 검사 로직
        time_str = decrypted_json.get('time')

        received_time = datetime.strptime(time_str, '%Y.%m.%d.%H.%M')
        current_time = timezone.now()
        # TODO. ⚠️10분 으로 변경 필요 (개발 중 이여서 100분으로 사용 중)
        QR_CODE_EXPIRY = timedelta(minutes=1)

        if current_time >= received_time + QR_CODE_EXPIRY:
            # current_time (Aware) >= received_time (Aware) + timedelta
            # 두 Aware 객체 간의 비교이므로 TypeError가 발생하지 않아야 합니다.
            return Response(
                {"detail": "QRCODE 인증 시간이 만료되어 사용이 불가합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )


        # 3. Remote Backend 검증 요청
        print("DEBUG decrypted_json : ", decrypted_json)
        device_check = {
            "dev_id" : decrypted_json['site'] +
                       decrypted_json['dong'] +
                       decrypted_json['ho']   +
                       decrypted_json['id'],
            "deviceId" : decrypted_json['deviceId']
        }

        api_response_data = Bootup.check_request(device_check)

        if api_response_data.get('status') is False:
            return Response(
                {"detail": "등록 되지 않은 환경제어기가 입니다. 등록 후 사용 해주세요."},
                status=status.HTTP_404_NOT_FOUND
            )
        # 4. 등록
        serializer = AuthRequestSerializer(data=decrypted_json, context={'request': request})

        print("api_response_data : " , api_response_data)


        # 4. Serializer를 통한 데이터 유효성 검사
        if serializer.is_valid():

            # 임시 응답 (성공)
            return Response(
                {"message": "인증 요청 데이터가 유효하며 처리 대기 중입니다.",
                 "data": serializer.validated_data},
                status=status.HTTP_200_OK
            )


        return Response(
            {
                "message": "인증 요청 데이터가 처리가 완료 되었습니다.",
                "site" : decrypted_json['site'],
                "dong" : decrypted_json['dong'],
                "ho" : decrypted_json['ho'],
                "id" : decrypted_json['id']
            },
            status=status.HTTP_200_OK
        )