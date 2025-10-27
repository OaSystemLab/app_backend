from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import OasGroup
from .serializers import UserRegistrationSerializer, UserLoginSerializer, OasGroupSerializer
from django.contrib.auth import login

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


class OasGroupListAPIView(generics.ListAPIView):
    # 어떤 모델 객체를 가져올지 지정합니다 (전체 객체)
    queryset = OasGroup.objects.all()

    # 가져온 객체를 어떤 Serializer로 변환할지 지정합니다
    serializer_class = OasGroupSerializer

    # 참고: 만약 특정 조건의 리스트만 보고 싶다면 get_queryset 메서드를 오버라이드합니다.
    # def get_queryset(self):
    #     return OasGroup.objects.filter(some_field='value')