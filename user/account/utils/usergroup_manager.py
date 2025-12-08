# util/usergroup_manager.py

from ..models import UserGroup # UserGroup 모델 import
from django.utils import timezone
from django.db import transaction # 원자적(Atomic) 트랜잭션 관리를 위해 추가
from django.db.models import QuerySet

class UserGroupManager:
    """
    UserGroup 모델의 생성, 업데이트를 전담하는 매니저 클래스
    """

    @classmethod
    @transaction.atomic
    def create_user_group_member(cls, **kwargs):
        """
        새로운 가족 그룹 구성원 레코드를 생성하고 반환합니다.

        Args:
            **kwargs: family_group_id, master_id, user_id, email, family_level 등의 필드 값

        Returns:
            UserGroup: 생성된 UserGroup 인스턴스

        Raises:
            ValueError: 필수 필드가 누락되었거나 데이터가 유효하지 않을 경우
        """

        # 1. 필수 필드 검증 (모델 정의에 따라 필수라고 가정한 필드)
        #required_fields = ['family_group_id', 'master_id', 'user_obj', 'email',  'family_level']
        required_fields = ['family_group_id', 'user_obj']
        for field in required_fields:
            if field not in kwargs or not kwargs[field]:
                raise ValueError(f"필수 필드 '{field}'가 누락되었습니다.")

        # 2. 기본값 설정 및 시간 설정
        # create_date는 모델에서 default=timezone.now로 설정했으므로,
        # kwargs에 포함하지 않아도 자동으로 현재 시간이 설정됩니다.

        try:
            # 3. 객체 생성 및 반환
            user_group_member = UserGroup.objects.create(
                family_group_id=kwargs['family_group_id'],
                #master_id=kwargs['master_id'],
                user=kwargs['user_obj'],
                # email=kwargs['email'],
                # nick_name=kwargs['nick_name'],
                # family_level=kwargs.get('family_level', 'user'), # 기본값 'user' 적용
                # create_date는 DB에서 자동으로 설정
            )
            return user_group_member

        except Exception as e:
            # 데이터베이스 제약 조건 위반 (예: Unique Constraint) 등의 오류 처리
            raise Exception(f"UserGroup 생성 중 오류 발생: {e}")

    @classmethod
    @transaction.atomic
    def update_user_group_member(cls, current_group_id: str, family_group_id: str, user_obj):
        # ... (생략: 필수 값 검증) ...

        # 1. 첫 번째 업데이트: user_obj를 제외한 사용자들의 family_level을 'user'로 변경

        # 쿼리셋 생성: current_group_id 이고 user_obj가 아닌 레코드
        queryset_except_user = UserGroup.objects.filter(
            family_group_id=current_group_id
        ).exclude(
            user=user_obj
        ).select_related('user') # 👈 연결된 UserInfo 객체를 미리 가져와 N+1 쿼리 방지

        updated_level_count = 0
        if queryset_except_user.exists():
            # 🚨 수정: 관계 필드 업데이트는 일괄 업데이트(update())가 불가능하므로,
            #           반복문을 사용하여 연결된 UserInfo 객체를 직접 업데이트하고 저장해야 합니다.
            for user_group_record in queryset_except_user:
                # 👈 UserGroup의 user 필드를 통해 UserInfo 객체에 접근
                if user_group_record.user.family_level != 'user':
                    user_group_record.user.family_level = 'user'
                    updated_level_count += 1
                user_group_record.user.family_group_id = family_group_id
                user_group_record.user.save() # 👈 UserInfo 객체를 저장

            print(f"INFO: {updated_level_count}개의 UserInfo family_level을 'user'로 변경 완료.")
        else:
            print(f"INFO: Level 변경 건너뜁니다.")


        # 2. 두 번째 업데이트: current_group_id 그룹 전체의 family_group_id를 새로운 ID로 변경

        # 이 부분은 UserGroup 자체 필드 업데이트이므로 QuerySet.update()를 그대로 사용합니다.
        queryset_all_members = UserGroup.objects.filter(
            family_group_id=current_group_id
        )

        if not queryset_all_members.exists():
            print(f"INFO: 레코드가 없어 그룹 ID 변경 건너뜁니다.")
            return

        # 일괄 업데이트 실행: family_group_id를 새로운 값으로 변경
        updated_group_count = queryset_all_members.update(
            family_group_id=family_group_id
        )

        print(f"INFO: {updated_group_count}개의 UserGroup family_group_id를 '{family_group_id}'로 변경 완료.")

        return updated_group_count