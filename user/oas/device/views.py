# oas/auth/device/views.py


from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle

from .models import OasGroup, OasInfo
from .serializers import  OasInfoSerializer, AuthRequestSerializer, OasInfoRoomUpdateSerializer, UserAppRequsetSerializer

from .utils.crypto import decrypt_qr_data_cryptography
from .utils.remote_manager import Bootup , AppMqttManager

# 시간 비교를 위한 import
from datetime import datetime, timedelta
from django.utils import timezone

from concurrent.futures import ThreadPoolExecutor

from .tasks import task_mqtt_broker_publish
# ----------------------------------------------------------------------
# 1. OasInfoRoomUpdateAPIView(환경 제어기 방이름 변경)
# ----------------------------------------------------------------------
class OasInfoRoomUpdateAPIView(APIView):
    """
    OasInfo 객체의 room 필드를 수정하는 API.
    로그인된 사용자 중 family_level='master'인 경우에만 수정이 가능합니다.
    """
    # 📌 권한 설정: 로그인된 사용자만 접근 허용
    permission_classes = [IsAuthenticated]

    # {
    #     "oas_info_id": 15,
    #     "new_room_name": "거실"
    # }

    def post(self, request, *args, **kwargs):
        # 1. Family Level 마스터 권한 확인
        user = request.user

        # ⚠️ 요청하신 대로 뷰 내부에서 master 레벨을 확인합니다.
        if user.family_level != 'master':
            return Response(
                {"detail": "이 작업을 수행할 권한이 없습니다. 가족 레벨이 'master'여야 합니다."},
                status=status.HTTP_403_FORBIDDEN # 권한 없음
            )

        # 2. 시리얼라이저를 사용하여 요청 데이터 검증
        serializer = OasInfoRoomUpdateSerializer(data=request.data)

        # 데이터 유효성 검사 실패 시 400 Bad Request 응답
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 3. 검증된 데이터 추출
        oas_info_id = serializer.validated_data['oas_info_id']
        new_room_name = serializer.validated_data['new_room_name']

        # 4. OasInfo 객체 조회 및 존재 여부 확인
        try:
            oas_info_instance = OasInfo.objects.get(pk=oas_info_id)
        except OasInfo.DoesNotExist:
            return Response(
                {"detail": f"ID {oas_info_id}에 해당하는 OasInfo 객체를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 5. 방 이름 (room) 필드 업데이트
        oas_info_instance.room = new_room_name
        oas_info_instance.save()

        # 6. 성공 응답 반환
        return Response(
            {
                "message": "방 이름이 성공적으로 수정되었습니다.",
                "oas_info_id": oas_info_id,
                "new_room_name": new_room_name
            },
            status=status.HTTP_200_OK
        )

# ----------------------------------------------------------------------
# 2. OasInfo List ViewSet (환경 제어기 상세 정보)
# ----------------------------------------------------------------------
class OasListAPIView(APIView):
    """
    현재 인증된 사용자 (UserInfo)가 가진 oas_group과 연결된
    OasGroup 객체가 참조하는 OasInfo 리스트를 반환합니다.
    URL: /oas_list/
    """
    # 📌 이 뷰는 로그인된 사용자만 접근 가능하도록 Permission 설정을 추가해야 합니다.
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. 현재 요청을 보낸 사용자 (UserInfo) 객체 가져오기
        user = request.user

        # 2. 사용자 객체에서 CharField인 oas_group_id 값 가져오기
        oas_group_id = user.oas_group_id

        # 3. oas_group_id 값이 없는지 확인
        if not oas_group_id:
            return Response(
                {"detail": "사용자에게 할당된 환경 제어기 그룹 ID가 없습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. OasGroup 객체 조회 (요청하신 filter() 구조 사용)
        oas_group_qs = OasGroup.objects.filter(oas_group_id=oas_group_id)

        # 5. 조회된 OasGroup이 없는 경우 처리
        if not oas_group_qs.exists():
             return Response(
                {"detail": f"ID '{oas_group_id}'에 해당하는 OasGroup이 존재하지 않습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 6. OasGroup QuerySet을 사용하여 연결된 OasInfo 객체들 가져오기
        # OasGroup.objects.filter(...)를 통해 OasInfo의 ID(pk)를 뽑아내고,
        # 이를 이용해 OasInfo 객체 QuerySet을 만듭니다. (중복 방지를 위해 distinct() 활용)

        # 연결된 OasInfo의 Primary Key (ID) 리스트 추출
        oas_info_pks = oas_group_qs.values_list('oas_info__pk', flat=True).distinct()

        # OasInfo 모델에서 해당 PK를 가진 모든 객체를 조회
        oas_info_list = OasInfo.objects.filter(pk__in=oas_info_pks)

        # 7. 시리얼라이즈 및 응답
        # 여러 객체를 시리얼라이즈하므로 반드시 many=True 옵션을 사용합니다.
        serializer = OasInfoSerializer(oas_info_list, many=True)

        # 결과는 JSON 배열 형태로 반환됩니다.
        return Response(serializer.data, status=status.HTTP_200_OK)
# ----------------------------------------------------------------------
# 3. Auth API View (환경 제어기 인증 요청 처리)
# ----------------------------------------------------------------------
MAX_FAIL_ATTEMPTS = 4 # 최대 연속 실패 횟수
class AuthAPIView(APIView):
    """
    환경 제어기 인증 요청을 처리하는 API입니다.
    POST 요청만 허용하며, 인증된 사용자(IsAuthenticated)만 접근 가능합니다.
    """
    # ⭐️ 인증된 사용자만 접근 가능하도록 설정합니다.
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user

        # 1. 기본 데이터 검증
        encrypted_data = request.data.get('data')
        if not encrypted_data:
            return Response(
                {"detail": "'data' 필드가 누락되었습니다."},
                status=status.HTTP_400_BAD_REQUEST
        )
        # 2. 복호화
        decrypted_json = decrypt_qr_data_cryptography(encrypted_data, request.user)

        if decrypted_json is None:

            # --- ⭐️ 계정 잠금 로직 시작 ⭐️ ---
            # 2.1. 실패 횟수 증가
            user.decryption_fail_count += 1
            user.last_fail_time = timezone.now()

            # 2.2. 4회 이상 실패 시 계정 비활성화
            if user.decryption_fail_count >= MAX_FAIL_ATTEMPTS:
                user.is_active = False # is_active 필드를 False로 설정 (계정 잠금)
                user.save(update_fields=['decryption_fail_count', 'last_fail_time', 'is_active'])

                # 계정 잠금 오류 응답
                return Response(
                    {"detail": "데이터 위변조가 감지 되었습니다. 15분 뒤에 다시 로그인 해주세요."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # 2.3. 모델 저장 및 실패 응답
            user.save(update_fields=['decryption_fail_count', 'last_fail_time'])

            return Response(
                #{"detail": f"데이터가 유효하지 않습니다. (연속 실패 횟수: {user.decryption_fail_count}/{MAX_FAIL_ATTEMPTS})"},
                {"detail": f"데이터가 유효하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
            # --- ⭐️ 계정 잠금 로직 종료 ⭐️ ---


        # 3. 복호화에 성공했다면, 연속 실패 카운트를 0으로 초기화
        if user.decryption_fail_count > 0:
            user.decryption_fail_count = 0
            user.last_fail_time = None
            user.save(update_fields=['decryption_fail_count', 'last_fail_time'])

        # 4. QRCODE 시간 유효성 검사 로직
        time_str = decrypted_json.get('time')
        received_time = datetime.strptime(time_str, '%Y.%m.%d.%H.%M')
        current_time = timezone.now()
        # TODO. ⚠️10분 으로 변경 필요
        QR_CODE_EXPIRY = timedelta(minutes=10)
        # TODO. 테스트 작업 으로 인해 주석 처리 함 2025.12.03 완료 이후 주석 삭제 필요.
        if current_time >= received_time + QR_CODE_EXPIRY:
            # current_time (Aware) >= received_time (Aware) + timedelta
            # 두 Aware 객체 간의 비교이므로 TypeError가 발생하지 않아야 합니다.
            return Response(
                {"detail": "QRCODE 인증 시간이 만료되어 사용이 불가합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )


        # 5. Remote Backend 검증 요청
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
        # 6. 등록
        serializer = AuthRequestSerializer(data=decrypted_json, context={'request': request})

        print("api_response_data : " , api_response_data)

        if serializer.is_valid():

            return Response(
                {
                    "detail": "인증 요청 데이터가 처리가 완료 되었습니다.",
                    "site" : decrypted_json['site'],
                    "site_name" : api_response_data.get('site_name'),
                    "dong" : decrypted_json['dong'],
                    "ho" : decrypted_json['ho'],
                    "id" : decrypted_json['id']
                },
                status=status.HTTP_200_OK
            )
        else :
            # 3. 오류 내용 확인 (가장 중요)
            print("❌ Serializer Validation Failed!")
            print("Serializer Errors:", serializer.errors)

            # 4. 오류 응답 반환
            return Response(
                serializer.errors['id'],
                status=status.HTTP_400_BAD_REQUEST
            )


# ----------------------------------------------------------------------
# 4. User app 에서 환경제어기 제어 명령
# ----------------------------------------------------------------------
# 전역으로 하나 생성
# 스레드 풀(Thread Pool) 사용
executor = ThreadPoolExecutor(max_workers=3)

class ThreePerMinUserThrottle(UserRateThrottle):
    # throttle_classes 요청을 분당 3번만 할 수 있다.
    rate = '10/min'

class UserAppOasRequest(APIView):
    """
    클라이언트로부터 site ID를 받아 외부 서버의 MQTT 정보를 반환하는 뷰
    - sitecode : stie(8) + dong(4) + ho(4) + id(1)

    sitecode = "116500010101021101"

    * site = data[0:8]   # 11650001
    * dong = data[8:12]  # 0101
    * ho = data[12:16] # 0211
    * id = data[16:17] # 0 (마지막 1자리만)

    result = f"{sitecode[:8]}-{sitecode[8:12]}-{sitecode[12:16]}-{sitecode[16:17]}"
    """
    permission_classes = [IsAuthenticated]  # 인증 사용자
    #throttle_classes = [ThreePerMinUserThrottle]    # 분당 10회 제한

    def post(self, request):
        # [1단계] 1차 필수 필드 존재 여부 검증
        required_fields = ['sitecode', 'type', 'action', 'option']
        if not all(field in request.data for field in required_fields):
            return Response(
                {"detail": "sitecode, type, action 필드는 필수입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # [2단계] Serializer를 통한 상세 유효성 검사
        serializer = UserAppRequsetSerializer(data=request.data)
        if not serializer.is_valid():
            print(serializer.errors)
            return Response({"detail": "처리할 수 없는 타입입니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 검증 완료된 데이터 사용
        valid_data = serializer.validated_data

        #AppMqttManager().broker_publish(valid_data)
        # [3단계] Celery 태스크로 비동기 처리 요청
        # .delay()를 사용하여 즉시 반환합니다.
        task_mqtt_broker_publish.delay(valid_data)

        #executor.submit(AppMqttManager().broker_publish, valid_data)
        # 사용자에게 즉각 응답
        return Response({
            "message": f"Site {valid_data['sitecode']} 제어 명령 접수",
            "action": valid_data['action']
        }, status=status.HTTP_202_ACCEPTED)

