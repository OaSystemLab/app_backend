# your_app/utils/user_management.py

from django.db import transaction
from rest_framework.exceptions import ValidationError
from log_events.models import ProjectLogEntry # ⭐️ 통합 모델 임포트
from account.models import UserGroup
from oas.device.models import OasGroup, OasInfo
from ..models import ApprovalRequest

# 필요한 모델 임포트 (UserInfo는 settings.AUTH_USER_MODEL을 통해 가져올 수도 있지만, 여기서는 직접 임포트 가정)
# from your_app.models import UserInfo, ApprovalRequest, ApprovalStatus
from django.contrib.auth import get_user_model
User = get_user_model() # UserInfo 모델을 가져옴

def update_user_info_on_approval(updated_request, requestee_level):
    """
    ApprovalRequest가 승인(APPROVED)되었을 때 요청자(requestee)의
    UserInfo를 업데이트하고, UserGroup 정보를 관리하는 핵심 비즈니스 로직.

    Args:
        updated_request (ApprovalRequest): 승인 완료된 ApprovalRequest 인스턴스.
        requestee_level (str): 요청자(requestee)의 현재 family_level ('master', 'user', 'none').
    """
    requestee = updated_request.requestee
    approver = updated_request.approver
    request_type = updated_request.request_type
    details = updated_request.details

    # 트랜잭션은 뷰에서 이미 시작되었지만, 여기서는 함수 내에서 독립적인 작업을
    # 수행하도록 구성하거나, 뷰의 트랜잭션을 신뢰하고 단순 업데이트만 수행할 수 있습니다.
    # 안전을 위해 뷰에서 트랜잭션을 시작했으므로, 여기서는 단순 업데이트만 수행합니다.

    # -----------------------------------------------------------------
    # 🌟 [요청 1] 요청자가 'user' 또는 'none' 레벨일 경우 처리 (그룹 가입) 🌟
    # -----------------------------------------------------------------
    # (요청자가 이미 master가 아니라서 그룹 가입이 필요한 경우)
    if requestee_level in ['user', 'none']:

        if request_type == 'group_join':

            approver_group_id = approver.family_group_id
            approver_oas_id = approver.oas_group_id

            if approver_group_id:
                # A. 요청자(requestee)의 필드 업데이트
                requestee.family_group_id = approver_group_id
                requestee.oas_group_id = approver_oas_id
                requestee.family_level = 'user' # 그룹에 가입했으므로 레벨 변경

                requestee.save(update_fields=['family_group_id', 'oas_group_id', 'family_level'])

                # B. UserGroup 모델 처리 (찾아서 업데이트하거나 새로 생성)
                try:
                    # primary_key가 user 필드이므로 get을 시도합니다.
                    user_group_instance = UserGroup.objects.get(user=requestee)

                    # 1. UserGroup 인스턴스가 존재하면 family_group_id 업데이트
                    user_group_instance.family_group_id = approver_group_id
                    user_group_instance.save(update_fields=['family_group_id'])

                    #user_group_action = "UserGroup 업데이트"

                except UserGroup.DoesNotExist:
                    # 2. UserGroup 인스턴스가 없으면 신규 생성
                    UserGroup.objects.create(
                        user=requestee,
                        family_group_id=approver_group_id
                    )
                    #user_group_action = "UserGroup 신규 생성"

                return " (일반 사용자 그룹 정보로 업데이트 완료)"
            else:
                # 승인자가 그룹 ID를 가지지 않은 경우 (데이터 불일치)
                # 승인자는 마스터 이기 때문에 무조건 family_group_id 를 가지고 있어야 한다.
                ProjectLogEntry.objects.create(
                    app_name='approval',
                    user=requestee,
                    level='ERROR',
                    event_type='update_user_info_on_approval',
                    message=f"승인자가 그룹 ID를 가지지 않은 경우 (데이터 불일치)",
                    request_data=f"{requestee.email}는 마스터 이기 때문에 무조건 family_group_id 를 가지고 있어야 한다"
                )
                raise ValidationError({'detail': '승인자에게 유효한 그룹 ID가 없어 가입 처리를 할 수 없습니다.'})

    # -----------------------------------------------------------------
    # 🌟 [요청 2] 요청자가 'master' 레벨일 경우 처리 (새로운 그룹 생성/할당 등의 복잡한 로직이 있을 수 있음) 🌟
    # -----------------------------------------------------------------
    elif requestee_level == 'master':
        # 요청자(Master)의 현재 그룹 ID를 가져옴
        target_group_id = requestee.family_group_id
        approver_group_id = approver.family_group_id
        approver_oas_id = approver.oas_group_id

        if request_type == 'group_join':

            # 1. OasGroup 매칭 QuerySet 준비
            oas_group_qs = OasGroup.objects.filter(oas_group_id=requestee.oas_group_id)

            oas_message = ""

            if oas_group_qs.exists():

                # 1.2. OasInfo PK 리스트를 메모리에 강제 로딩 (list() 사용)
                # 이 시점에 DB 쿼리가 실행되어 PK 값이 메모리에 저장됩니다.
                oas_info_pks = list(oas_group_qs.values_list('oas_info__pk', flat=True))

                # 1.3. [순서 1] 참조하는 객체 (자식)인 OasGroup 먼저 삭제
                # ProtectedError를 피하기 위해 OasGroup을 OasInfo보다 먼저 삭제합니다.
                deleted_oas_group_count, _ = oas_group_qs.delete()
                oas_message += f", {deleted_oas_group_count}개의 OasGroup 삭제"

                print("1 oas_message : ", oas_message)

                # 1.4. [순서 2] 참조되는 객체 (부모)인 OasInfo 삭제
                # oas_info_pks는 이제 Python list이므로 OasGroup 삭제와 무관하게 사용 가능합니다.
                if oas_info_pks:
                    deleted_oas_info_count, _ = OasInfo.objects.filter(pk__in=oas_info_pks).delete()
                    oas_message += f", {deleted_oas_info_count}개의 OasInfo 삭제"

                print("2 oas_message : ", oas_message)


            # 2. Master의 그룹 ID를 이용해 UserGroup에서 해당 그룹 멤버들을 찾음
            # UserGroup은 family_group_id를 필드로 가지고 있음
            users_in_group_qs = UserGroup.objects.filter(family_group_id=target_group_id)

            # 3. 해당 UserGroup 인스턴스들의 user_id(UserInfo)를 가져와 일괄 업데이트 준비
            # * Master는 해당 그룹에서 탈퇴하려는 시점일 수 있으므로, Master를 포함한 전체 그룹원을 업데이트합니다.
            user_pks = users_in_group_qs.values_list('user__pk', flat=True)

            print("user_pks :" ,user_pks)
            # 4. UserInfo 일괄 업데이트 (해당 그룹 멤버 전체를 None으로 초기화)
            # queryset.update()는 트랜잭션 내에서 안전하게 동작합니다.
            updated_count = User.objects.filter(pk__in=user_pks).update(
                family_group_id=None,
                oas_group_id=None,
                family_level='none' # 'none'은 CharField choices에 있으므로 문자열로 설정
            )

            # 5. UserGroup 레코드 일괄 삭제 (선택적: 그룹 해체)
            # UserGroup 레코드 자체를 삭제합니다.
            deleted_count, _ = users_in_group_qs.delete()


            # 6. 요청자 정보 apperver 정보로 변경
            requestee.family_group_id = approver_group_id
            requestee.oas_group_id = approver_oas_id
            requestee.family_level = 'user' # 그룹에 가입했으므로 레벨 변경

            requestee.save(update_fields=['family_group_id', 'oas_group_id', 'family_level'])
            # 7. 5번에서 일괄 삭제 했기 때문에 새로 생성
            UserGroup.objects.create(
                user=requestee,
                family_group_id=approver_group_id
            )

            # 8. 승인 요청 내용 삭제.
            deletion_queryset = ApprovalRequest.objects.filter(requestee=requestee)
            deletion_queryset.delete()

            #return f" (Master 탈퇴 처리: 그룹 '{target_group_id}'의 사용자 {updated_count}명 UserInfo 해제 및 {deleted_count}개 UserGroup 레코드 삭제 완료)"

        elif request_type == 'MASTER_DEMOTE': # Master 권한 해제 요청이라고 가정
             # Master 권한을 해제하는 로직 (요청자 본인만 user/none으로 강등)
             pass


    # -----------------------------------------------------------------
    # 🌟 기타 요청 유형 처리 (필요 시) 🌟
    # -----------------------------------------------------------------
    # (다른 request_type에 대한 업데이트 로직을 여기에 추가합니다.)

    return "" # 아무런 업데이트도 일어나지 않았을 경우 빈 문자열 반환