# oas/auth/device/views.py

from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import OasGroup, OasInfo
from .serializers import OasGroupSerializer, OasInfoSerializer, AuthRequestSerializer
from rest_framework.permissions import IsAuthenticated

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
class AuthAPIView(APIView):
    """
    환경 제어기 인증 요청을 처리하는 API입니다.
    POST 요청만 허용하며, 인증된 사용자(IsAuthenticated)만 접근 가능합니다.
    """
    # ⭐️ 인증된 사용자만 접근 가능하도록 설정합니다.
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        print("request.data : ", request.data)
        serializer = AuthRequestSerializer(data=request.data, context={'request': request})

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