
import asyncio
from adrf.views import APIView
from asgiref.sync import sync_to_async
from django.http import JsonResponse
#from .services import TDengineService

#from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

import logging
from oas.device.models import OasGroup # 모델 위치에 맞춰 수정하세요
from tdengine.services import td_service, db_service, ChartService
from .redis_pool import cleanup_async_redis_pool

from .serializers import DeviceSearchSerializer, DashboardSerializer, ChartRequestSerializer

def api_latest_data(request, sitecode):
    #service = TDengineService()
    data = td_service.get_latest_data(sitecode)

    if data:
        return JsonResponse({"status": "success", "data": data})
    return JsonResponse({"status": "error", "message": "No data found"}, status=404)


# 에러 로그 기록을 위해 설정
logger = logging.getLogger(__name__)

# 🟢 1. SimpleJWT의 동기 DB 조회를 안전한 스레드로 격리하는 래퍼 함수
@sync_to_async
def get_authenticated_user(request):
    authenticator = JWTAuthentication()
    try:
        # 토큰 검증 및 DB 유저 조회 (동기로 작동하지만 sync_to_async 덕분에 안전함)
        auth_result = authenticator.authenticate(request)
        if auth_result is not None:
            return auth_result[0] # user 객체 반환
        return None
    except (InvalidToken, AuthenticationFailed):
        return None
class DeviceRefreshView(APIView):
    """
    사용자의 환경제어기(OAS) 장비 목록과 최신 상태, 센싱 데이터를 비동기(Async)로 갱신(Refresh)하는 API 뷰입니다.

    대규모 동시 접속 환경에서 Redis 및 DB I/O 대기 시간으로 인한 워커(Worker) 병목을 방지하기 위해
    100% 비동기 논블로킹(Non-blocking) 방식으로 구현되었습니다. 장비가 여러 대일 경우 asyncio.gather를
    통해 데이터를 병렬로 수집하여 응답 속도를 극대화합니다.

    Attributes:
        authentication_classes (list): DRF 입구에서의 동기식 토큰 검증(DB 쿼리)이 비동기 이벤트 루프를
                                       블로킹(SynchronousOnlyOperation)하는 것을 방지하기 위해 빈 리스트([])로 강제 설정합니다.
        permission_classes (list): DRF 기본 권한 검사를 차단하기 위해 빈 리스트([])로 강제 설정합니다.

    Methods:
        get(request):
            뷰 내부에서 수동으로 비동기 인증을 수행한 후, 사용자의 장비 그룹 정보를 비동기 ORM으로 조회합니다.
            이후 각 장비의 하트비트(통신 상태)와 최신 센싱 데이터를 Redis 비동기 풀을 이용해 병렬로 수집하여 반환합니다.
    """
    authentication_classes = []
    permission_classes = []

    async def get(self, request):
        try:
            # 뷰 내부에서 비동기적으로 인증 함수 호출
            user = await get_authenticated_user(request)

            # 권한 체크 (IsAuthenticated 역할 대체)
            if not user:
                return Response({
                    "status": "error",
                    "message": "유효하지 않은 토큰이거나 인증되지 않았습니다."
                }, status=status.HTTP_401_UNAUTHORIZED)

            # 1. 사용자의 그룹에 속한 장치들이 있는지 확인 (비동기 DB 조회)
            user_oas_groups = []

            # async for를 사용하여 DB 쿼리를 비동기적으로 실행하고 결과를 리스트에 담습니다.
            async for group in OasGroup.objects.filter(
                oas_group_id=user.oas_group_id
            ).select_related('oas_info'):
                user_oas_groups.append(group)

            # 만약 장치가 하나도 없다면 여기서 빠르게 응답을 종료합니다.
            if not user_oas_groups:
                return Response({
                    'status': 'success',
                    'dev': []
                }, status=status.HTTP_200_OK)

            tasks = []
            for group in user_oas_groups:
                # 각 장비의 데이터를 가져오는 '작업 지시서(Task)'를 만듭니다.
                tasks.append(self.fetch_device_data(group))

            # 생성된 모든 작업을 '동시에' 실행하고, 모두 끝날 때까지 기다립니다.
            # 장비가 1대든 2000대든, 순차 처리에 비해 속도가 비약적으로 상승합니다.
            dev_list = await asyncio.gather(*tasks)

            # 3. 최종 결과 반환
            return Response({
                'status': 'success',
                'dev': dev_list
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": "서버 내부 오류",
                "error_detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            # 응답을 반환하기 직전에 Redis 커넥션을 명시적으로 닫아줍니다.
            await cleanup_async_redis_pool()

    async def fetch_device_data(self, group):
        """개별 장비의 데이터를 비동기로 가져와서 딕셔너리로 조립하는 함수"""
        oas = group.oas_info
        sitecode = f"{oas.site}{oas.dong}{oas.ho}{oas.oas_id}"

        heartbeat_result, sensing_data = await asyncio.gather(
            db_service.get_heartbeat_status_async(sitecode),
            db_service.redis_get_sensing_async(sitecode)
        )

        # 반환값 언패킹
        h_status, tstring, last_seen = heartbeat_result

        # 조립 후 반환
        return {
            'id': oas.oas_id,
            'sitecode': sitecode,
            'room_name': oas.room,
            'status': h_status,
            'tsring': tstring,
            'last_seen': last_seen,
            'data': sensing_data
        }
# 2026-04-16 비동기화 방식으로 변형. 이슈 없으면 삭제 필요.
class DeviceRefreshView2(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user

            # 1. 사용자의 그룹에 속한 장치들이 있는지 확인
            user_oas_groups = OasGroup.objects.filter(
                oas_group_id=user.oas_group_id
            ).select_related('oas_info')

            dev_list = []

            # 2. 루프를 돌며 데이터 수집
            for group in user_oas_groups:
                oas = group.oas_info
                # sitecode 생성 규칙 유지
                sitecode = f"{oas.site}{oas.dong}{oas.ho}{oas.oas_id}"

                # 2026-04-06 redis 변경
                h_status, tstring, last_seen =  db_service.get_heartbeat_status(sitecode)

                dev_list.append({
                    'id' : group.oas_info.oas_id,
                    'sitecode' : sitecode,
                    'room_name' : group.oas_info.room,
                    'status' : h_status,
                    'tsring' : tstring,
                    'last_seen' : last_seen,
                    'data' : db_service.redis_get_sensing(sitecode)
                })

            # 3. 최종 결과 반환
            return Response({
                'status': 'success',
                'dev': dev_list
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # 예상치 못한 서버 내부 에러 처리
            # logger.error(f"Unexpected Error in DeviceRefreshView: {str(e)}")
            return Response({
                'status': 'error',
                # 'message': '서버 내부 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeviceSearchView(APIView):
    """
    TDengine에서 특정 장비의 시계열 이력 데이터를 비동기(Async)로 검색하는 API 뷰입니다.
    DRF의 동기 인증 프레임워크가 이벤트 루프를 블로킹하는 것을 방지하기 위해
    클래스 레벨 인증을 해제하고 내부에서 비동기 인증을 처리합니다.
    """
    authentication_classes = []
    permission_classes = []

    async def post(self, request):
        try:
            # 1. 비동기 환경 인증
            user = await get_authenticated_user(request)
            if not user:
                return Response({
                    "status": "error",
                    "message": "인증 실패"
                }, status=status.HTTP_401_UNAUTHORIZED)

            # 2. Serializer를 통한 1차 검증 (동기 처리 가능)
            serializer = DeviceSearchSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'status': 'error',
                    'message': '데이터 검증 실패',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            v_data = serializer.validated_data

            # 3. 비동기 Service 호출 (메서드명에 _async를 붙이고 await 사용)
            # td_service가 전역 객체라면 그대로 쓰고, 아니라면 인스턴스를 생성하세요.
            if v_data['data_type'] == 'hourly':
                history_data = await td_service.get_hourly_data_async(
                    sitecode=v_data['sitecode'],
                    select_clause=v_data['select_clause'],
                    start_time=v_data['start_time'],
                    end_time=v_data['end_time']
                )
            elif v_data['data_type'] == 'row':
                history_data = await td_service.get_history_data_async(
                    sitecode=v_data['sitecode'],
                    select_clause=v_data['select_clause'],
                    start_time=v_data['start_time'],
                    end_time=v_data['end_time']
                )
            else:
                history_data = await td_service.get_day_night_data_async(
                    sitecode=v_data['sitecode'],
                    select_clause=v_data['select_clause'],
                    start_time=v_data['start_time'],
                    end_time=v_data['end_time']
                )

            return Response({
                'status': 'success',
                'count': len(history_data) if history_data else 0,
                'data': history_data
            }, status=status.HTTP_200_OK)

        except ValueError as ve:
            # 보안 위반 등 로직 에러 처리
            return Response({'status': 'error', 'message': str(ve)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({'status': 'error', 'message': '서버 내부 오류', 'error_detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DeviceSearchView2(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 1. Serializer를 통한 1차 검증
        serializer = DeviceSearchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': '데이터 검증 실패',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        v_data = serializer.validated_data

        try:
            # 2. 서비스 호출 (검증된 데이터 전달)
            if v_data['data_type'] == 'hourly':
                history_data = td_service.get_hourly_data(
                    sitecode=v_data['sitecode'],
                    select_clause=v_data['select_clause'], # 리스트 그대로 전달
                    start_time=v_data['start_time'],
                    end_time=v_data['end_time']
                )
            elif v_data['data_type'] == 'row':
                history_data = td_service.get_history_data(
                    sitecode=v_data['sitecode'],
                    select_clause=v_data['select_clause'],
                    start_time=v_data['start_time'],
                    end_time=v_data['end_time']
                )
            else:
                history_data = td_service.get_day_night_data(
                    sitecode=v_data['sitecode'],
                    select_clause=v_data['select_clause'],
                    start_time=v_data['start_time'],
                    end_time=v_data['end_time']
                )

            return Response({
                'status': 'success',
                'count': len(history_data),
                'data': history_data
            }, status=status.HTTP_200_OK)

        except ValueError as ve:
            # 보안 위반 등 로직 에러 처리
            return Response({'status': 'error', 'message': str(ve)}, status=403)
        except Exception as e:
            return Response({'status': 'error', 'message': '서버 내부 오류'}, status=500)



class DashBoardView(APIView):
    """
    환경제어기 대시보드 데이터를 비동기(Async)로 조회하는 API 뷰입니다.
    """
    # DRF 동기 검증 차단
    authentication_classes = []
    permission_classes = []

    async def post(self, request):
        try:
            # 1. 비동기 환경 인증
            user = await get_authenticated_user(request)
            if not user:
                return Response({
                    "status": "error",
                    "message": "인증 실패"
                }, status=status.HTTP_401_UNAUTHORIZED)

            # 2. Serializer를 통한 검증
            # 참고: Serializer의 is_valid() 자체는 동기 작업이지만,
            # DB 조회를 유발하지 않는 단순 문자열/형식 검증이라면 비동기 뷰 안에서 그냥 써도 무방합니다.
            serializer = DashboardSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'status': 'error',
                    'message': '데이터 검증 실패',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            v_data = serializer.validated_data

            # 3. 비동기 Service 호출 (await)
            # db_service가 전역 객체인지, 지역 생성 객체인지에 따라 맞게 사용하세요.
            #db_service = DashboardService()
            r_data = await db_service.get_dashboard_async(v_data)

            # 매칭되지 않은 data_type 처리
            if r_data is None:
                r_data = []

            return Response({
                'status': 'success',
                'count': len(r_data) if isinstance(r_data, (list, dict)) else 1,
                'data': r_data
            }, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response({'status': 'error', 'message': str(ve)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({'status': 'error', 'message': '서버 내부 오류'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 4. 🚀 [필수] 루프 종료 전 Redis 커넥션 누수 방지
        finally:
            await cleanup_async_redis_pool()

class DashBoardView2(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 1. Serializer를 통한 1차 검증
        serializer = DashboardSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': '데이터 검증 실패',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        v_data = serializer.validated_data

        try:
            r_data = []

            match v_data['data_type']:
                case "a1" | "a2" | "a3":
                    r_data = db_service.get_dashboard(v_data)
                case _: # 그 외 나머지 (default)
                        r_data = None

            return Response({
                'status': 'success',
                'count': len(r_data),
                'data': r_data
            }, status=status.HTTP_200_OK)

        except ValueError as ve:
            # 보안 위반 등 로직 에러 처리
            return Response({'status': 'error', 'message': str(ve)}, status=403)
        except Exception as e:
            return Response({'status': 'error', 'message': '서버 내부 오류'}, status=500)

# 2026-04-16 비동기화 방식으로 변형. 이슈 없으면 삭제 필요.
class ChartView2(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChartRequestSerializer(data=request.data)

        if serializer.is_valid():
            sitecode = serializer.validated_data['sitecode']
            data_type = serializer.validated_data['data_type']

            try:
                # Service 호출
                data = ChartService().get_sensor_chart_data(sitecode, data_type)

                return Response({
                    "sitecode": sitecode,
                    "data_type": data_type,
                    "count": len(data),
                    "chart_data": data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChartView(APIView):
    """
    환경제어기의 개별 센서 차트 데이터를 비동기(Async)로 조회하는 API 뷰입니다.

    DRF의 기본 동기(Sync) 인증 프레임워크가 이벤트 루프를 블로킹하는 현상(SynchronousOnlyOperation)을
    방지하기 위해, 클래스 레벨의 자동 인증을 비활성화하고 뷰 내부에서 안전하게 비동기 인증을 직접 수행합니다.

    Attributes:
        authentication_classes (list): DRF 입구에서의 동기식 토큰 검증을 원천 차단하기 위해 빈 리스트([])로 강제 설정합니다.
        permission_classes (list): DRF 입구에서의 동기식 권한 검사를 차단하기 위해 빈 리스트([])로 강제 설정합니다.

    Methods:
        post(request):
            내부적으로 비동기 인증을 거친 후, 클라이언트의 요청(sitecode, data_type)을 받아
            Redis Stream에서 시계열 차트 데이터를 조회하고 파싱하여 반환합니다.
    """
    authentication_classes = []
    permission_classes = []

    async def post(self, request):
        try:
            # 1. 비동기 인증 수행
            user = await get_authenticated_user(request)
            if not user:
                return Response({
                    "status": "error",
                    "message": "인증되지 않은 사용자입니다."
                }, status=status.HTTP_401_UNAUTHORIZED)

            serializer = ChartRequestSerializer(data=request.data)

            if serializer.is_valid():
                sitecode = serializer.validated_data['sitecode']
                data_type = serializer.validated_data['data_type']

                # 2. Service 비동기 호출
                service = ChartService()
                data = await service.get_sensor_chart_data_async(sitecode, data_type)

                return Response({
                    "sitecode": sitecode,
                    "data_type": data_type,
                    "count": len(data),
                    "chart_data": data
                }, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                "status": "error",
                "message": "차트 데이터 조회 중 오류 발생",
                "error_detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 🚀 [핵심 추가] Redis 커넥션 누수 방지
        finally:
            await cleanup_async_redis_pool()