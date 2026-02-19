from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F # 필드 값을 참조하기 위해 F 객체 import
from ..models import UserInfo, UserGroup # UserGroup 모델을 추가했습니다.

class GroupService:
    """가족 그룹 관리와 관련된 비즈니스 로직을 처리하는 서비스 클래스"""

    @staticmethod
    @transaction.atomic # @transaction.atomic 데코레이터를 사용하여 트랜잭션을 적용합니다.
    def transfer_master_authority_with_group_id_change(current_master_user_id: int, new_master_user_id: int):
        """
        마스터 권한을 new_master_user_id에게 이양하고,
        기존 그룹의 family_group_id를 새 마스터의 ID 기반으로 변경합니다.

        :param current_master_user_id: 현재 로그인된 (권한을 넘길) 마스터의 UserInfo PK
        :param new_master_user_id: 마스터 권한을 넘겨받을 대상 UserInfo PK
        :return: (성공 여부: bool, 메시지: str)
        """
        try:
            # 1. 사용자 객체 조회 (동시성 문제를 위해 select_for_update 사용)
            # UserInfo와 UserGroup 모두에 영향을 미치므로, Lock을 잡습니다.

            # 대상 사용자들을 업데이트를 위해 잠급니다.
            users_to_update = UserInfo.objects.select_for_update().filter(
                pk__in=[current_master_user_id, new_master_user_id]
            ).prefetch_related('usergroup') # UserGroup도 함께 가져옵니다.

            current_master = next((user for user in users_to_update if user.pk == current_master_user_id), None)
            new_master = next((user for user in users_to_update if user.pk == new_master_user_id), None)

            if not current_master or not new_master:
                raise UserInfo.DoesNotExist("요청된 사용자(들)를 찾을 수 없습니다.")

            # 2. 유효성 검사
            if current_master.family_level != 'master':
                raise PermissionDenied("권한 이양을 요청한 사용자(`{}`)는 현재 그룹 마스터가 아닙니다.".format(current_master.nick_name))

            old_family_group_id = current_master.family_group_id
            if not old_family_group_id:
                raise ValidationError("현재 마스터는 어떤 그룹에도 소속되어 있지 않습니다.")

            if old_family_group_id != new_master.family_group_id:
                raise ValidationError("새 마스터 후보는 현재 마스터와 동일한 그룹에 소속되어 있지 않습니다.")

            if current_master.pk == new_master.pk:
                raise ValidationError("자기 자신에게 마스터 권한을 양도할 수 없습니다.")

            # 3. 새로운 가족 그룹 ID 생성
            new_family_group_id = f"fam_{new_master_user_id}"

            if new_family_group_id == old_family_group_id:
                 raise ValidationError("새 그룹 ID가 기존 그룹 ID와 동일합니다. 로직 오류 가능성이 있습니다.")

            # 4. 권한 및 그룹 ID 일괄 변경 (핵심 로직)

            # 4-1. UserInfo 테이블 업데이트
            # 기존 그룹 ID를 가진 모든 멤버의 family_group_id를 새로운 ID로 일괄 변경합니다.
            UserInfo.objects.filter(family_group_id=old_family_group_id).update(
                family_group_id=new_family_group_id
            )

            # 4-2. UserGroup 테이블 업데이트
            # 기존 그룹 ID를 가진 UserGroup 레코드의 family_group_id도 일괄 변경합니다.
            UserGroup.objects.filter(family_group_id=old_family_group_id).update(
                family_group_id=new_family_group_id
            )

            # 4-3. family_level 업데이트

            # 새 마스터에게 'master' 권한 부여
            UserInfo.objects.filter(pk=new_master.pk).update(family_level='master')

            # 기존 마스터를 'user'로 강등 (PK로 특정)
            UserInfo.objects.filter(pk=current_master.pk).update(family_level='user')

            # 객체를 메모리에서 새로 로드하여 변경 사항을 반영
            current_master.refresh_from_db()
            new_master.refresh_from_db()

            return True, f"마스터 권한이 '{new_master.nick_name}'님에게 성공적으로 이양되었으며, 그룹 ID가 '{new_family_group_id}'로 변경되었습니다."

        except UserInfo.DoesNotExist:
            return False, "요청된 사용자(들)를 찾을 수 없습니다."
        except (PermissionDenied, ValidationError) as e:
            # 트랜잭션 내에서 발생한 유효성/권한 오류는 Rollback됩니다.
            return False, str(e)
        except Exception as e:
            # 치명적인 오류 발생 시 트랜잭션은 자동으로 Rollback됩니다.
            # 로깅 처리 필요
            print(f"Master transfer fatal error: {e}")
            return False, "마스터 권한 이양 및 그룹 ID 변경 중 알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

    @staticmethod
    @transaction.atomic # 트랜잭션을 사용하여 두 모델의 작업이 동시에 실행되도록 보장
    def leave_family_group(user_id: int):
        """
        가족 그룹을 탈퇴하고 관련 정보를 초기화합니다.

        - 마스터인 경우: 권한 이양 필요 예외 발생
        - 유저/없음인 경우: UserGroup 삭제 및 UserInfo 그룹 정보 초기화

        :param user_id: 탈퇴를 요청한 사용자의 UserInfo PK
        :return: (성공 여부: bool, 메시지: str)
        """
        try:
            # 1. 사용자 객체 조회 및 Lock
            # DB Lock을 걸어 동시성 문제 방지
            user = UserInfo.objects.select_for_update().get(pk=user_id)

            # 2. 마스터 권한 확인 (탈퇴 불가 조건)
            if user.family_level == 'master':
                # 마스터는 반드시 권한을 이양해야만 탈퇴할 수 있습니다.
                raise PermissionDenied(
                    "현재 사용자({nickname})는 가족 그룹의 마스터입니다. 그룹을 탈퇴하려면 먼저 '마스터 권한 이양' 기능을 사용하여 다른 멤버에게 권한을 넘겨주어야 합니다.".format(
                        nickname=user.nick_name
                    )
                )

            # 3. 그룹 소속 여부 확인 및 초기화
            if user.family_group_id is None or user.family_level == 'none':
                return True, "사용자({})는 이미 어떤 가족 그룹에도 소속되어 있지 않습니다. (탈퇴 완료)".format(user.nick_name)

            # 4. 일반 사용자 탈퇴 실행 ('user' 또는 'none' 레벨)

            # 4-1. UserGroup 레코드 삭제
            try:
                # user_id가 UserGroup의 PK로 설정되어 있으므로 이를 이용해 삭제
                user_group_instance = UserGroup.objects.get(pk=user_id)
                user_group_instance.delete()
            except UserGroup.DoesNotExist:
                # UserGroup 레코드가 없을 경우, 에러 없이 다음 단계 진행
                pass

            # 4-2. UserInfo 그룹 정보 초기화
            user.family_level = 'none' # 그룹에 소속되지 않은 상태로 변경
            user.family_group_id = None # 그룹 ID 초기화 (Charfield의 경우 None 또는 빈 문자열)

            # 5. 환경제어기 Group ID 초기화
            user.oas_group_id = None

            user.save(update_fields=['family_level', 'family_group_id', 'oas_group_id'])

            return True, "사용자({})님의 가족 그룹 탈퇴가 성공적으로 완료되었습니다.".format(user.nick_name)

        except UserInfo.DoesNotExist:
            return False, "요청된 사용자를 찾을 수 없습니다."
        except PermissionDenied as e:
            # 마스터 권한으로 인한 탈퇴 불가 예외 처리
            return False, str(e)
        except Exception as e:
            # 기타 오류 처리 및 트랜잭션 롤백
            print(f"Family group leave fatal error: {e}")
            return False, "가족 그룹 탈퇴 중 알 수 없는 오류가 발생했습니다."

    @staticmethod
    @transaction.atomic # 트랜잭션을 사용하여 작업의 원자성(Atomicity)을 보장
    def kick_member_from_group(master_user_id: int, target_user_id: int):
        """
        마스터가 특정 멤버를 가족 그룹에서 추방합니다.

        :param master_user_id: 추방을 요청한 마스터의 UserInfo PK
        :param target_user_id: 추방 대상 멤버의 UserInfo PK
        :return: (성공 여부: bool, 메시지: str)
        """
        try:
            # 1. 사용자 객체 조회 및 Lock
            # Lock을 걸어 동시성 문제 방지 (두 사용자 모두에 대해)
            users_to_update = UserInfo.objects.select_for_update().filter(
                pk__in=[master_user_id, target_user_id]
            )

            master = next((user for user in users_to_update if user.pk == master_user_id), None)
            target_user = next((user for user in users_to_update if user.pk == target_user_id), None)

            if not master or not target_user:
                raise UserInfo.DoesNotExist("요청된 사용자(들)를 찾을 수 없습니다.")

            # 2. 권한 및 유효성 검사

            # 2-1. 요청자가 마스터인지 확인
            if master.family_level != 'master':
                raise PermissionDenied("추방 권한이 없습니다. 요청자(`{}`)는 그룹 마스터가 아닙니다.".format(master.nick_name))

            # 2-2. 마스터가 속한 그룹이 있는지 확인
            master_group_id = master.family_group_id
            if not master_group_id:
                raise ValidationError("마스터(`{}`)는 현재 어떤 그룹에도 소속되어 있지 않습니다.".format(master.nick_name))

            # 2-3. 대상이 동일 그룹에 속하는지 확인
            if target_user.family_group_id != master_group_id:
                raise ValidationError("추방 대상(`{}`)은 마스터와 동일한 그룹에 소속되어 있지 않습니다.".format(target_user.nick_name))

            # 2-4. 자기 자신 추방 불가
            if master.pk == target_user.pk:
                raise ValidationError("마스터는 자기 자신을 추방할 수 없습니다. 탈퇴 기능을 사용해 주세요.")

            # 2-5. 추방 대상이 이미 그룹 멤버가 아닌지 확인 (이중 추방 방지)
            if target_user.family_level == 'none':
                 return True, f"사용자('{target_user.nick_name}')는 이미 그룹에 소속되어 있지 않습니다. (추방 완료)"


            # 3. 추방 실행 (데이터 초기화 및 삭제)

            # 3-1. UserInfo 필드 초기화
            target_user.oas_group_id = None
            target_user.family_group_id = None
            target_user.family_level = 'none' # 그룹에 소속되지 않은 상태로 변경
            target_user.save(update_fields=['oas_group_id', 'family_group_id', 'family_level'])

            # 3-2. UserGroup 레코드 삭제
            # UserGroup의 PK가 user_id이므로 이를 이용해 삭제
            UserGroup.objects.filter(pk=target_user_id).delete()

            return True, f"사용자('{target_user.nick_name}')를 가족 그룹에서 성공적으로 추방했습니다."

        except UserInfo.DoesNotExist:
            return False, "요청된 사용자(들)를 찾을 수 없습니다."
        except (PermissionDenied, ValidationError) as e:
            # 권한 및 유효성 오류 처리
            return False, str(e)
        except Exception as e:
            # 기타 오류 처리 및 트랜잭션 롤백
            print(f"Family group kick fatal error: {e}")
            return False, "멤버 추방 중 알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."