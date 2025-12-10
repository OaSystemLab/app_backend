from rest_framework import serializers
from django.db.models import Q
from .models import ApprovalRequest, ApprovalStatus # .models는 실제 모델 파일 경로에 맞게 수정 필요
from django.utils import timezone

class ApprovalRequestSerializer(serializers.ModelSerializer):
    """
    ApprovalRequest 모델의 데이터를 직렬화 및 역직렬화하고,
    'PENDING' 상태의 중복 요청을 검증합니다.
    """

    class Meta:
        model = ApprovalRequest
        # requestee와 request_type은 요청 시 전달되어야 합니다.
        fields = (
            'id', 'requestee', 'approver', 'request_type',
            'details', 'status', 'requested_at',
            'approved_or_rejected_at', 'reason'
        )
        # 읽기 전용 필드를 명시하여 실수로 수정되는 것을 방지
        read_only_fields = ('requested_at', 'approved_or_rejected_at')


    def validate(self, data):
        """
        요청자(requestee)가 동일한 요청 유형(request_type)에 대해
        이미 '대기 중(PENDING)'인 요청을 가지고 있는지 확인합니다.
        """
        # 요청자(requestee)와 요청 유형(request_type) 데이터를 가져옵니다.
        # 이 데이터는 역직렬화(Deserialization) 과정에서 들어온 데이터입니다.
        requestee = data.get('requestee')
        request_type = data.get('request_type')

        # 요청자를 지정하지 않은 경우 (이럴 일은 거의 없지만 안전을 위해)
        if not requestee or not request_type:
             # Serializer 필드 레벨에서 검증되거나, 요청자가 인증된 사용자라면 자동으로 설정될 수 있습니다.
             # 여기서는 기본적으로 필드가 존재한다고 가정합니다.
             return data

        # 쿼리셋을 사용하여 'PENDING' 상태의 중복 요청이 있는지 확인합니다.
        # Q 객체를 사용하여 status='pending' 조건으로 필터링합니다.
        # ApprovalStatus.PENDING은 'pending' 문자열을 나타냅니다.
        has_pending_request = ApprovalRequest.objects.filter(
            requestee=requestee,
            request_type=request_type,
            status=ApprovalStatus.PENDING
        ).exists()

        if has_pending_request:
            # 중복 요청이 발견되면 유효성 검사 오류(ValidationError)를 발생시킵니다.
            raise serializers.ValidationError(
                {'detail': '이미 해당 요청 유형에 대한 대기 중인 승인 요청이 있습니다. 요청이 처리될 때까지 새로운 요청을 할 수 없습니다.'}
            )

        # 모든 검증을 통과하면 데이터 반환
        return data

    def update(self, instance, validated_data):
        """
        승인/거부 시 status 및 approved_or_rejected_at 필드를 업데이트합니다.
        """
        new_status = validated_data.get('status', instance.status)
        reason = validated_data.get('reason', instance.reason)

        # 1. 상태 변경이 실제로 발생했는지 확인
        if instance.status != new_status:
            # 2. 상태가 PENDING에서 APPROVED 또는 REJECTED로 변경되는지 확인
            if new_status in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:

                # approved_or_rejected_at 필드에 현재 시각을 기록
                instance.approved_or_rejected_at = timezone.now()

            elif new_status == ApprovalStatus.PENDING:
                # PENDING으로 다시 변경할 경우 처리 시각은 초기화
                instance.approved_or_rejected_at = None

            else:
                # 기타 상태 변경 (예: CANCELED는 이 API에서 처리하지 않음)
                pass

        # reason 필드 업데이트
        instance.reason = reason
        # status 필드 업데이트
        instance.status = new_status

        instance.save()
        return instance