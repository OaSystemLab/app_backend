# Create your views here.
from django.http import JsonResponse
#from .services import TDengineService

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
import logging
from oas.device.models import OasGroup # 모델 위치에 맞춰 수정하세요
from tdengine.services import td_service, db_service

from .serializers import DeviceSearchSerializer, DashboardSerializer

def api_latest_data(request, sitecode):
    #service = TDengineService()
    data = td_service.get_latest_data(sitecode)

    if data:
        return JsonResponse({"status": "success", "data": data})
    return JsonResponse({"status": "error", "message": "No data found"}, status=404)


# 에러 로그 기록을 위해 설정
logger = logging.getLogger(__name__)

class DeviceRefreshView(APIView):
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

                dev_list.append({
                    'id' : group.oas_info.oas_id,
                    'sitecode' : sitecode,
                    'room_name' : group.oas_info.room,
                    'data' : td_service.get_latest_data(sitecode)
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

