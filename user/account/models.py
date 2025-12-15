from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin
)
from django.utils import timezone
from django.core.mail import send_mail
from .managers import UserInfoManager # managers.py에서 매니저를 가져옵니다.


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
    # email 인증 코드
    email_auth_code = models.CharField(
        verbose_name='이메일 인증 코드',
        max_length=10,
        null=True,
        blank=True
    )
    # email 인증 코드 사용 주기 설정을 위해
    email_code_date = models.DateTimeField(
        verbose_name='코드 생성 날짜',
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
    email_reauth_date = models.DateTimeField(
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
        max_length=254, # 표준 권장 254 RFC 5321 Section 4.5.3.1
        unique=True,
        null=False
    )
    # 👇 이메일 변경 요청 시 새로운 이메일을 임시로 저장할 필드 추가
    new_email = models.EmailField(
        verbose_name='새 이메일 (변경 대기 중)',
        max_length=254, # 표준 권장 254 RFC 5321 Section 4.5.3.1
        unique=False,
        null=True,     # 이메일 변경 요청이 없을 때는 None
        blank=True
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

    # 👇 [추가: 인증 실패 추적 및 계정 잠금 관련 필드]
    decryption_fail_count = models.IntegerField(
        verbose_name='복호화 연속 실패 횟수',
        default=0,
        null=False,
    )

    last_fail_time = models.DateTimeField(
        verbose_name='마지막 복호화 실패 시간',
        null=True,
        blank=True,
    )

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



class UserGroup(models.Model):
    """
    가족 그룹 내 사용자 등록 및 관계 정보를 관리하는 모델
    """

    # 1. family_group_id: 가족 그룹 ID
    family_group_id = models.CharField(
        max_length=50,
        verbose_name="가족 그룹 ID",
        help_text="가족 그룹을 식별하는 고유 ID (예: fam_1)"
    )

    # 2. master_id: family_level 마스터 ID
    # master_id = models.CharField(
    #     max_length=50,
    #     verbose_name="Family Level 마스터",
    #     help_text="그룹 내 마스터 권한을 가진 사용자 ID(User 모델 참조)"
    # )

    # 3. user_id: user_info id (실제 사용자 본인 ID)
    # user_id = models.BigIntegerField(
    #     verbose_name="사용자 ID",
    #     help_text="그룹에 소속된 사용자 (User 모델 참조)",
    #     unique=True
    # )

    user = models.OneToOneField(
        'UserInfo', # 👈 실제 UserInfo 모델 클래스 이름을 사용해야 합니다.
        on_delete=models.CASCADE, # 👈 UserInfo 삭제 시 UserGroup도 함께 삭제
        primary_key=True, # 👈 이 필드를 UserGroup의 기본 키(PK)로 사용 (추천)
        verbose_name="사용자 ID",
        help_text="그룹에 소속된 사용자 (UserInfo 모델과 1:1 연결)"
    )


    # # 4. email: 이메일 (user 기준)
    # email = models.CharField(
    #     max_length=254, # 이메일 최대 길이 (표준 권장 RFC 5321 Section 4.5.3.1)
    #     verbose_name="이메일",
    #     help_text="사용자 기준 이메일"
    # )

    # # 5. nick_name: 닉 네임 (user 기준)
    # nick_name = models.CharField(
    #     max_length=50,
    #     verbose_name="닉네임",
    #     help_text="사용자 기준 닉네임"
    # )

    # # 6. family_level: 가족 레벨 (master, user)
    # FAMILY_LEVEL_CHOICES = [
    #     ('master', '마스터'),
    #     ('user', '일반 사용자'),
    # ]
    # family_level = models.CharField(
    #     max_length=10,
    #     choices=FAMILY_LEVEL_CHOICES,
    #     default='user',
    #     verbose_name="가족 레벨",
    #     help_text="그룹 내 권한 레벨 (master 또는 user)"
    # )

    # 7. create_date: 생성 일자
    create_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="생성 일자"
    )

    class Meta:
        verbose_name = "가족 그룹"
        verbose_name_plural = "가족 그룹"
        db_table = 'user_group' # 데이터베이스 테이블명을 user_info로 설정

    def __str__(self):
        return f"{self.family_group_id}"




class EmailLog(models.Model):
    """
    이메일 전송 시도 및 최종 실패 기록을 위한 모델
    """
    email = models.EmailField(
        verbose_name="대상 이메일"
    )
    task_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Celery 작업 ID"
    )
    log_type = models.CharField(
        max_length=50,
        default='FAILURE',
        verbose_name="로그 타입 (SUCCESS/FAILURE 등)"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name="오류 메시지"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="기록 시간"
    )

    class Meta:
        verbose_name = "이메일 로그"
        verbose_name_plural = "이메일 로그"
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.log_type}] {self.email} - {self.created_at.strftime("%Y-%m-%d %H:%M:%S")}'