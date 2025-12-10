from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied

# 모델 및 시리얼라이저 임포트 (경로에 맞게 수정 필요)
from .models import ApprovalRequest, ApprovalStatus
from .serializers import ApprovalRequestSerializer
from .utils.cooldown import RequestCooldownManager
# User 모델 임포트 (settings.AUTH_USER_MODEL을 직접 사용하거나, 실제 모델 경로 임포트)
from django.conf import settings

from account.models import UserInfo as User

UserModel = settings.AUTH_USER_MODEL # settings.AUTH_USER_MODEL을 참조하는 것이 권장됩니다.

# POST
# {
#     "master_email": "hsh@oasiss.co.kr",
#     "request_type" : "group_join"
# }
# DELETE
# {
#     "request_type": "group_join"
# }

class ApprovalRequestAPIView(APIView):
    """
    POST 요청을 통해 새로운 승인 요청(ApprovalRequest)을 생성합니다.
    - 요청자(requestee)는 현재 로그인된 사용자입니다.
    - 승인자(approver)는 요청된 master_email을 가진 사용자입니다.
    """
    # 사용자가 인증되었는지 확인하는 권한 설정
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. 필수 데이터 확인
        master_email = request.data.get('master_email')
        request_type = request.data.get('request_type')


        # request.data에 details(JSON) 필드가 있다면 함께 처리합니다.
        details = request.data.get('details', {})

        # 필드가 누락되었는지 확인
        if not master_email or not request_type:
            return Response(
                {'detail': 'master_email과 request_type은 필수 필드입니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 요청자 및 승인자 찾기
        requestee = request.user # 현재 로그인된 사용자

        # *** 쿨다운 검사: 유틸리티 클래스 사용 ***
        cooldown_manager = RequestCooldownManager(requestee, request_type)
        try:
            cooldown_manager.check_and_enforce_cooldown()
        except ValidationError as e:
            # 쿨다운 중이면 429 응답을 반환합니다.
            return Response(
             {
                 'detail': e.detail['detail'],
             },
             status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        # ***********************************

        try:
            # master_email을 통해 승인자를 찾습니다.
            approver = User.objects.get(email=master_email)
        except User.DoesNotExist:
            return Response(
                {'detail': f'이메일 {master_email} 을 가진 승인자(Master)를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # **추가 검증: 승인자가 실제로 마스터 권한을 가지고 있는지 확인 (필요하다면)**
        if not approver.family_level == 'master':
            return Response(
                {'detail': '지정된 사용자는 승인 권한이 없습니다.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Serializer에 전달할 최종 데이터 구성
        # requestee와 approver는 인스턴스 자체를 전달합니다.
        data_for_serializer = {
            'requestee': requestee.pk, # Serializer는 PK를 기대합니다.
            'approver': approver.pk,
            'request_type': request_type,
            'details': details, # JSON 필드 데이터
            'status': ApprovalStatus.PENDING, # 항상 PENDING으로 시작
        }

        # 4. Serializer를 사용하여 데이터 검증 및 저장
        serializer = ApprovalRequestSerializer(data=data_for_serializer)

        if serializer.is_valid():
            # serializer.save()를 호출하면 validate 로직을 거쳐 DB에 저장됩니다.
            approval_request = serializer.save()

            # 성공 응답
            return Response(
                {
                    'detail': '승인 요청이 성공적으로 진행 되었습니다.'
                },
                status=status.HTTP_201_CREATED
            )
        else:
            # 중복 요청을 포함한 모든 Serializer 유효성 검사 오류 응답
            return Response(
                {
                    'detail': serializer.errors['detail'][0],
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request, *args, **kwargs):
        """요청자(request.user)의 PENDING 상태 요청을 찾아 삭제합니다."""
        # 1. 요청 유형 데이터 확인
        request_type = request.data.get('request_type')

        if not request_type:
            return Response(
                {'detail': 'request_type은 필수 필드입니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 요청 객체 찾기
        # requestee = 현재 사용자
        # request_type = 요청 받은 유형
        # status = PENDING (대기 중인 요청만 취소 가능)
        try:
            approval_request = ApprovalRequest.objects.get(
                requestee=request.user,
                request_type=request_type,
                status=ApprovalStatus.PENDING # 대기 중인 요청만 취소/삭제 가능
            )
        except ApprovalRequest.DoesNotExist:
            # 적합한 대기 중인 요청이 없는 경우
            return Response(
                {'detail': f'대기 중인 요청이 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 3. 데이터베이스에서 요청 레코드 삭제
        # .delete() 메서드를 호출하여 레코드를 삭제하고 결과를 받습니다.
        delete_result = approval_request.delete()

        # 4. *** 쿨다운 기록 설정: 유틸리티 클래스 사용 ***
        cooldown_manager = RequestCooldownManager(request.user, request_type)
        cooldown_manager.set_cooldown()
        # **********************************************

        # 5. 응답
        return Response(
            {
                'detail': f'취소 요청이 완료 되었습니다.'
            },
            status=status.HTTP_204_NO_CONTENT # 삭제 성공 시 204 No Content 권장
        )



class PendingApprovalCheckAPIView(APIView):
    """
    GET: 현재 로그인된 사용자(request.user)에게 들어온 PENDING 상태의
    승인 요청이 존재하는지 여부를 True/False로 응답합니다.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. 로그인된 사용자를 승인자(approver)로 지정하여 PENDING 요청을 모두 조회
        pending_requests = ApprovalRequest.objects.filter(
            approver=request.user,
            status=ApprovalStatus.PENDING
        ).order_by('requested_at') # 요청된 순서대로 정렬 (선택 사항)

        # 2. 요청 존재 여부 확인
        has_pending_requests = pending_requests.exists()

        # 3. 요청 목록 직렬화
        # 다수의 객체를 직렬화하므로 many=True 설정
        # list에 필요한 필드만 포함하도록 ApprovalRequestSerializer를 사용하거나,
        # 목록 전용의 경량 Serializer를 사용하는 것이 더 효율적입니다.
        # (여기서는 전체 Serializer를 사용한다고 가정합니다.)
        serializer = ApprovalRequestSerializer(pending_requests, many=True)

        # 4. 응답 구성
        response_data = {
            'status': has_pending_requests, # 요청 존재 여부
            'list': serializer.data        # 요청 목록 (없으면 빈 리스트)
        }

        # 5. 결과 응답
        return Response(
            response_data,
            status=status.HTTP_200_OK
        )
# {
#     "status": "approved",
#     "reason": "요청 사항이 규정에 부합함"
# }
class ApprovalRequestUpdateAPIView(APIView):
    """
    PATCH: 특정 ID의 승인 요청 상태(status)를 승인자(approver)가 업데이트합니다.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, request_id, *args, **kwargs):
        # 1. 요청 객체 가져오기
        try:
            approval_request = ApprovalRequest.objects.get(pk=request_id)
        except ApprovalRequest.DoesNotExist:
            raise NotFound({'error': '해당 ID의 승인 요청을 찾을 수 없습니다.'})

        # 2. 권한 검증: 현재 로그인된 사용자가 승인자인지 확인
        if approval_request.approver != request.user:
            raise PermissionDenied({'error': '해당 요청을 처리(승인/거부)할 권한이 없습니다.'})

        # 3. 데이터 검증: status와 reason만 받도록 제한
        allowed_fields = ['status', 'reason']
        rdata = {k: v for k, v in request.data.items() if k in allowed_fields}

        # 4. 상태 유효성 검사: PENDING 상태에서만 승인/거부 가능하도록 제한
        new_status = rdata.get('status')
        if new_status and new_status != approval_request.status:
            if approval_request.status != ApprovalStatus.PENDING:
                raise ValidationError({'status': f'현재 상태({approval_request.get_status_display()})에서는 상태를 변경할 수 없습니다. (처리 완료됨)'})

            if new_status not in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:
                raise ValidationError({'status': '상태는 APPROVED 또는 REJECTED로만 변경할 수 있습니다.'})

            if new_status == ApprovalStatus.REJECTED and not rdata.get('reason'):
                raise ValidationError({'reason': '요청을 거부(REJECTED)할 경우 사유(reason)를 반드시 입력해야 합니다.'})

        # 5. Serializer를 사용하여 업데이트
        # partial=True 설정으로 일부 필드만 업데이트 허용
        serializer = ApprovalRequestSerializer(
            approval_request,
            data=rdata,
            partial=True
        )

        if serializer.is_valid(raise_exception=True):
            updated_request = serializer.save()

            return Response(
                {
                    'message': f'요청 ID {request_id}가 {updated_request.get_status_display()} 상태로 변경되었습니다.',
                    'data': ApprovalRequestSerializer(updated_request).data
                },
                status=status.HTTP_200_OK
            )