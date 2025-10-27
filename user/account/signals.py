# signals.py 파일은 **Django Signals (시그널)**이라는 기능을 구현하는 곳입니다.
#
# 쉽게 말해, Django의 특정 동작(이벤트)이 발생했을 때 다른 동작(함수)을 자동으로 실행하도록 연결해
# 주는 **"알림 및 반응 시스템"**의 역할을 합니다.
#
# 1. signals.py의 역할: UserEmail 자동 생성
# 이 파일은 UserInfo 모델의 인스턴스가 데이터베이스에 **처음 저장(생성)**될 때(이벤트),
# UserEmail 모델의 인스턴스도 자동으로 생성하도록(반응) 연결하는 역할을 합니다.

#구성       요소	            역할
#이벤트     (Signal)	        post_save (저장이 완료된 후)
#발신자     (Sender)	        UserInfo 모델
#수신자     (Receiver/Handler)	create_user_email 함수
#작동 방식	 UserInfo 객체가 생성되어 DB에 저장되면,
#           Django가 post_save 시그널을 발생시키고,
#           create_user_email 함수가 이 시그널을 받아 새로운 UserEmail 객체를 생성합니다.

# 2. 왜 signals.py를 사용하나요?
# 모델의 로직이 단순한 필드 정의를 넘어 다른 모델과의 연쇄적인 동작을 필요로 할 때 유용합니다.
# 자동화: UserInfo 생성 시마다 수동으로 UserEmail을 만들 필요가 없습니다.
# Decoupling (결합 해제): UserInfo 모델 자체에는 UserEmail을 생성하는 코드가 포함되어 있지 않아 모델 코드가 깔끔하게 유지됩니다.
# 일관성: Django의 모든 저장 경로(Admin, API, Shell 등)에서 이 규칙이 일관되게 적용됩니다.


from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UserInfo, UserEmail

# UserInfo가 저장(생성 또는 수정)된 후 실행될 함수
@receiver(post_save, sender=UserInfo)
def create_or_update_user_email(sender, instance, created, **kwargs):
    """
    새로운 UserInfo 인스턴스가 생성되면 해당 사용자를 위한 UserEmail 인스턴스를 생성합니다.
    """
    # created=True 일 때만 UserEmail을 생성합니다.
    if created:
        UserEmail.objects.create(user=instance)

    # 사용자가 기존에 존재하고, UserEmail이 이미 있다면, 여기서 update 로직을 추가할 수 있습니다.
    # 현재는 기본값 자동 생성만 요청하셨으므로, 생성 로직만 포함합니다.
