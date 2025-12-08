import json
from django.db import transaction

from ..utils.oas_manager import OasInfoSearchDeviceIdLock, OasInfoNewObject, OasGroupCreateObject, OasInfoDelete, OasUpdateProcess
from account.utils.usergroup_manager import UserGroupManager

class OasSetupService:
    """OAS 그룹이 없는 사용자에게 신규 그룹 및 관련 정보를 설정하는 서비스."""

    @classmethod
    @transaction.atomic
    def setup_new_group(cls, user, initial_data):
        """
        user.oas_group_id가 None일 때 실행되는 전체 로직.

        Args:
            user (UserInfo): 현재 요청 사용자 객체.
            initial_data (dict): Serializer의 원시 입력 데이터 (deviceId, site 등).

        Returns:
            str: 새로 생성된 oas_group_id
        """

        # ⭐조건. deviceId 검색 전부 Lock 처리
        if not OasInfoSearchDeviceIdLock(initial_data['deviceId']):
            raise Exception("DeviceId Lock 처리 중 오류가 발생했습니다.") # 예외는 View/Serializer에서 처리

        # ✅ 체크. family_levle master 생성
        family_level = "master"
        # ✅ 체크. family_group_id 생성
        family_group_id = "fam_" + str(user.id)

        # 1. UserGroup 레코드 생성/업데이트 로직
        if user.family_group_id is None:
            # UserGroup 레코드 생성 (이전 논의된 create_user_group_member 사용)
            member_data = {
                "family_group_id": family_group_id,
                "master_id": str(user.id),
                "user_obj": user,
                "family_level": family_level,
            }
            # ✅ 체크. user group 생성
            UserGroupManager.create_user_group_member(**member_data)
        else:
            # UserGroup 레코드 업데이트 (이전 논의된 update_user_group_member 사용)
            if user.family_level != "master":
                UserGroupManager.update_user_group_member(
                    current_group_id=user.family_group_id,
                    family_group_id=family_group_id,
                    user_obj=user
                )

        # 2. UserInfo 정보 업데이트 및 저장
        user.family_group_id = family_group_id
        user.family_level = family_level
        user.save()

        # 3. OAS 객체 생성 로직 (oas_group_id, oas_info_id 처리)
        # ℹ️ 기준이 oas_group_id 없는 경우 이기 때문에 기존 생성 여부는 체크 하지 안는다.
        # id 생성
        oas_group_id = "oas_group_" + str(user.id)
        # oas_info 생성
        oas_info_id = OasInfoNewObject(initial_data)

        if oas_info_id is None:
            raise Exception("OAS 정보 생성 중 오류가 발생했습니다.")
        # oas group 생성
        oas_group_id_created = OasGroupCreateObject(oas_group_id, oas_info_id.id)

        if oas_group_id_created is None:
            OasInfoDelete(oas_info_id.id)
            raise Exception("OAS 그룹 생성 중 오류가 발생했습니다.")

        user.oas_group_id = oas_group_id
        user.save()

        return oas_group_id_created # 최종 생성된 ID 반환

    @classmethod
    @transaction.atomic
    def setup_update_group(cls, user, initial_data):
        """
        1. oas_group_id 가 있는 이유는 등록 사용자인 경우(신규, 가족 추가, 디바이스 인증)
        2. oas_group_id 에 있는 oas_info_id 를 이용해 deviceId 찾기 <br>
        2.1 있는 경우.<br>
        ⭐ 체크. site, dong, ho 매칭 해서 같으면 oas_group_id 안에 있는 oas_info_id 중 Lock 있으면 해제<br>
        ⭐ 체크. site, dong, ho 매칭 해서 틀린 oas_info_id 삭제 후 새로 oas_info 생성<br>
        2.2 없는 경우.<br>
        ⭐ 체크. site, dong, ho 매칭 해서 같으면 oas_info_id 추가 후 oas_group_id 에 추가 등록<br>
        ⭐ 체크. site, dong, ho 매칭 해서 틀린 oas_info_id 삭제 후 oas_info_id 추가 후 oas_group_id 에 추가 등록<br>
        3. oas_group_id 를 해당 user_id 맞게 변경(이유. 제어기 인증은 master 변경 하기 때문에 해다 유저 로 변경)<br>
        4. family_group_id 확인 하여 신규 생성 및 업데이트<br>
        4.1 없는 경우.<br>
        ⭐ 체크. 환경제어기 신규 등록시 family_group_id 가 생성 되는데 버그 등로 인해 생성이 안된 경우를 위해 새로 생성
        family_level,  family_group_id 새로 구성 하여 생성함
        4.2 있는 경우<br>
        ⭐ 체크. 환경제어기 인증이 들어 왔기 때문에 family_level 을 무조건 master 변경 하는 작업으로 진행
        """

        oas_group_id = "oas_group_" + str(user.id)

        if OasUpdateProcess.DeviceId(user, initial_data) is not None:

            OasUpdateProcess.GroupID(user, oas_group_id)

            user.oas_group_id = oas_group_id
            user.save()

            # ✅ 체크. family_levle master 생성
            family_level = "master"
            # ✅ 체크. family_group_id 생성
            family_group_id = "fam_" + str(user.id)

            # 1. UserGroup 레코드 생성/업데이트 로직
            if user.family_group_id is None:
                # UserGroup 레코드 생성 (이전 논의된 create_user_group_member 사용)
                member_data = {
                    "family_group_id": family_group_id,
                    "master_id": str(user.id),
                    "user_obj": user,
                    "family_level": family_level,
                }
                # ✅ 체크. user group 생성
                UserGroupManager.create_user_group_member(**member_data)
            else:
                # UserGroup 레코드 업데이트 (이전 논의된 update_user_group_member 사용)
                if user.family_level != "master":
                    UserGroupManager.update_user_group_member(
                        current_group_id=user.family_group_id,
                        family_group_id=family_group_id,
                        user_obj=user
                    )

            # 2. UserInfo 정보 업데이트 및 저장
            user.family_group_id = family_group_id
            user.family_level = family_level
            user.save()