from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin
)
from django.utils import timezone
from django.core.mail import send_mail
from .managers import UserInfoManager # managers.py에서 매니저를 가져옵니다.



# OasGroup Model Definition (환경 제어기 등록 정보)
class OasGroup(models.Model):
    # oas_group_id를 기본키로 사용
    oas_group_id = models.CharField(
        verbose_name='환경 제어 그룹 ID',
        max_length=50,
    )
    oas_info_id = models.CharField(
        verbose_name='환경 제어기 정보 ID',
        max_length=50
    )
    oas_name = models.CharField(
        verbose_name='사용자 정의 제어기 이름',
        max_length=100,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        verbose_name='생성 날짜',
        auto_now_add=True # 객체 최초 생성 시 자동 저장
    )

    class Meta:
        verbose_name = '환경 제어기 등록 정보'
        verbose_name_plural = '환경 제어기 등록 정보'
        db_table = 'oas_group'

    def __str__(self):
        return self.oas_group_id


# OasInfo Model Definition (환경 제어기 정보)
class OasInfo(models.Model):
    # id 필드는 기본적으로 Django가 Primary Key로 자동 생성합니다.
    stie = models.CharField(
        verbose_name='지역 코드',
        max_length=10
    )
    dong = models.CharField(
        verbose_name='아파트 동',
        max_length=4
    )
    ho = models.CharField(
        verbose_name='아파트 호',
        max_length=4
    )
    oas_id = models.CharField(
        verbose_name='환경 제어기 ID',
        max_length=2
    )
    device_id = models.CharField(
        verbose_name='환경 제어기 Device ID',
        max_length=20,
        unique=True
    )
    # room 필드의 VARBINARY(100) 타입은 Django의 BinaryField로 매핑합니다.
    # 이미지 스펙에 따라 null=True 허용
    room = models.BinaryField(
        verbose_name='원격 관리에서 정해진 방 이름',
        max_length=100,
        null=True,
        blank=True
    )
    auth = models.BooleanField(
        verbose_name='환경 제어기 인증 상태',
        default=False
    )
    auth_count = models.SmallIntegerField(
        verbose_name='환경 제어기 인증 횟수',
        default=0
    )
    # 이미지 스펙에 따라 날짜/시간 유형 필드 설정
    auth_date = models.DateField( # DATE(6) 스펙에 따라 DateField로 설정
        verbose_name='환경 제어기 인증 날짜',
        null=True,
        blank=True
    )
    lock = models.BooleanField(
        verbose_name='잠금 상태',
        default=False
    )
    lock_date = models.DateField( # DATE 스펙에 따라 DateField로 설정
        verbose_name='잠김 날짜',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        verbose_name='생성 날짜',
        auto_now_add=True # 객체 최초 생성 시 자동 저장
    )

    class Meta:
        verbose_name = '환경 제어기 정보'
        verbose_name_plural = '환경 제어기 정보'
        db_table = 'oas_info'
        # 지역 코드, 동, 호, oas_id 조합은 고유해야 할 가능성이 높아 unique_together로 설정합니다.
        unique_together = (('stie', 'dong', 'ho', 'oas_id'),)

    def __str__(self):
        return f'{self.device_id} ({self.stie}-{self.dong}-{self.ho})'



# user_email 모델 (이미지 기반)
class UserEmail(models.Model):
    """
    사용자 이메일 인증 관련 정보를 저장하는 모델.
    UserInfo와 1:1 관계를 가지며, UserInfo 삭제 시 연쇄 삭제(CASCADE)됩니다.
    """
    # UserInfo 모델과의 1:1 관계 설정. user 삭제 시 이메일 레코드도 삭제됩니다.
    user = models.OneToOneField(
        'UserInfo',
        on_delete=models.CASCADE,
        related_name='email_info', # UserInfo.email_info로 접근 가능
        verbose_name='사용자'
    )

    # 이미지 기반 필드 정의
    email_auth = models.BooleanField(
        verbose_name='이메일 인증 상태',
        default=False,
        null=False
    )
    email_auth_count = models.SmallIntegerField(
        verbose_name='이메일 인증 횟수',
        default=0,
        null=False
    )
    email_auth_date = models.DateField(
        verbose_name='이메일 인증 날짜',
        null=True,
        blank=True
    )
    email_auth_code = models.CharField(
        verbose_name='이메일 인증 코드',
        max_length=10,
        null=True,
        blank=True
    )
    email_refresh_count = models.SmallIntegerField(
        verbose_name='이메일 다시 전송 횟수',
        default=0,
        null=False
    )
    email_auth_lock = models.BooleanField(
        verbose_name='이메일 인증 잠김',
        default=False,
        null=False
    )
    email_lock_time = models.DateTimeField(
        verbose_name='이메일 잠김 시간',
        null=True,
        blank=True
    )
    email_reauth_count = models.SmallIntegerField(
        verbose_name='이메일 재 인증 횟수',
        default=0,
        null=False
    )
    email_reauth_lock = models.BooleanField(
        verbose_name='이메일 재 인증 잠김',
        default=False,
        null=False
    )
    email_reauth_date = models.DateField(
        verbose_name='이메일 재 인증 잠김 날짜', # 이미지에는 '이메일 재 인증 잠김'이지만 Date 필드이므로 '날짜'로 변경
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = '사용자 이메일'
        verbose_name_plural = '사용자 이메일'
        db_table = 'user_email'

    def __str__(self):
        return f'{self.user.email} - Email Info'

# user_info 모델 (AbstractBaseUser와 PermissionsMixin 상속)
class UserInfo(AbstractBaseUser, PermissionsMixin):
    """
    이미지에서 요청된 필드들을 포함하는 커스텀 사용자 모델입니다.
    email을 USERNAME_FIELD로 사용하여 로그인에 사용합니다.
    """
    # [기본 사용자 정보]
    # email을 고유하게 설정하고, USERNAME_FIELD로 지정합니다.
    email = models.EmailField(
        verbose_name='이메일',
        max_length=100,
        unique=True,
        null=False
    )

    # 비밀번호는 AbstractBaseUser에 의해 기본적으로 처리됩니다.

    # [커스텀 필드]
    family_level = models.CharField(
        verbose_name='가족 레벨',
        max_length=20, # 10에서 20으로 증가
        choices=[('master', 'master'), ('user', 'user'), ('none', 'none')], # Choices 추가
        default='none', # 기본값 'none' 설정
        # unique=True 필드 제거 (Choices 필드에 Unique는 일반적으로 사용하지 않음)
        null=False # default='none'이 있으므로 필수 필드로 유지
    )

    nick_name = models.CharField(
        verbose_name='닉네임',
        max_length=50,
        #unique=True, # 이미지에서 UQ 요구
        null=False, # REQUIRED_FIELDS에 포함되었으므로 False로 변경
        blank=False # REQUIRED_FIELDS에 포함되었으므로 False로 변경
    )

    oas_group_id = models.CharField(
        verbose_name='환경제어 그룹 ID',
        max_length=50,
        #unique=True, # 이미지에서 UQ 요구
        null=True,
        blank=True
    )

    # 이미지에서 unique: True, default: 0 로 설정된 인증 중인 가족 수
    family_auth_count = models.SmallIntegerField(
        verbose_name='인증 중인 가족 수',
        default=0,
        null=False,
    )

    family_group_id = models.CharField(
        verbose_name='가족 그룹 ID',
        max_length=50,
        #unique=True, # 이미지에서 UQ 요구
        null=True,
        blank=True
    )

    # [AbstractBaseUser 기본 필드 오버라이딩 및 추가 권한]

    # 계정이 활성 상태인지 여부 (계정 잠금 기능) - 이미지에 따라 default=True
    is_active = models.BooleanField(
        verbose_name='계정 활성 상태',
        default=True,
        null=False
    )

    # 관리자 사이트 접근 여부 - 이미지에 따라 default=False
    is_staff = models.BooleanField(
        verbose_name='관리자 사이트 접근',
        default=False,
        null=False
    )

    # 최고 권한자 여부 - 이미지에 따라 default=False
    is_superuser = models.BooleanField(
        verbose_name='최고 권한자',
        default=False,
        null=False
    )

    # 생성 날짜 (date_joined는 AbstractBaseUser에 기본적으로 포함되어 있지 않으므로 수동 추가)
    date_joined = models.DateTimeField(
        verbose_name='생성 날짜',
        default=timezone.now
    )

    # last_login 필드는 AbstractBaseUser에 의해 기본적으로 처리됩니다.
    # groups와 user_permissions는 PermissionsMixin에 의해 처리됩니다.

    objects = UserInfoManager() # 커스텀 매니저 연결

    # 필수 설정: USERNAME_FIELD와 REQUIRED_FIELDS
    USERNAME_FIELD = 'email' # 로그인 시 사용할 필드
    # REQUIRED_FIELDS는 create_superuser 시 USERNAME_FIELD와 password를 제외하고 필수로 입력받을 필드 목록입니다.
    # nick_name만 필수 필드에 포함합니다.
    REQUIRED_FIELDS = ['nick_name']

    class Meta:
        verbose_name = '사용자 정보'
        verbose_name_plural = '사용자 정보'
        db_table = 'user_info' # 데이터베이스 테이블명을 user_info로 설정

    def __str__(self):
        return self.email

    # 이메일 전송 관련 편의 메서드 (선택 사항)
    def get_full_name(self):
        # 전체 이름을 반환합니다. 닉네임이 있다면 닉네임, 없다면 이메일을 반환
        return self.nick_name or self.email

    def get_short_name(self):
        # 짧은 이름을 반환합니다.
        return self.nick_name or self.email.split('@')[0]

    def email_user(self, subject, message, from_email=None, **kwargs):
        """사용자에게 이메일을 보냅니다."""
        send_mail(subject, message, from_email, [self.email], **kwargs)
