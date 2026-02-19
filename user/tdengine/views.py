# Create your views here.
from django.http import JsonResponse
#from .services import TDengineService

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
import logging
from oas.device.models import OasGroup # 모델 위치에 맞춰 수정하세요
from tdengine.services import td_service

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
        try:
            # 1. POST 데이터 추출
            sitecode = request.data.get('sitecode')
            select_list = request.data.get('select_clause', []) # 리스트 형태
            start_time = request.data.get('start_time')
            end_time = request.data.get('end_time')
            data_type = request.data.get('data_type')
            # 데이터 유효성 검사 (필수 값 확인)
            if not all([sitecode, select_list, start_time, end_time, data_type]):
                return Response({
                    'status': 'error',
                    'message': '필수 데이터(sitecode, select_clause, start_time, end_time, data_type)가 누락되었습니다.'
                }, status=status.HTTP_400_BAD_REQUEST)
            # 3. TDengine 서비스 호출
            select_str = ", ".join(select_list)

            #print(request.data)

            if data_type == 'hourly':
                history_data = td_service.get_hourly_data(
                    sitecode=sitecode,
                    select_clause=select_str,
                    start_time=start_time,
                    end_time=end_time
                )
            else:
                history_data = td_service.get_history_data(
                    sitecode=sitecode,
                    select_clause=select_str,
                    start_time=start_time,
                    end_time=end_time
                )

            # history_data = td_service.get_history_data(
            #     sitecode=sitecode,
            #     select_clause=select_str,
            #     start_time=start_time,
            #     end_time=end_time
            # )
            # 3. 최종 결과 반환
            return Response({
                'status': 'success',
                'count': len(history_data),
                'data': history_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # 예상치 못한 서버 내부 에러 처리
            # logger.error(f"Unexpected Error in DeviceRefreshView: {str(e)}")
            return Response({
                'status': 'error',
                # 'message': '서버 내부 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)