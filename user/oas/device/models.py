from django.db import models

# Create your models here.


# OasGroup Model Definition (환경 제어기 등록 정보)
class OasGroup(models.Model):
    # oas_group_id를 기본키로 사용
    oas_group_id = models.CharField(
        verbose_name='환경제어기 그룹 ID',
        max_length=50,
    )
    # oas_info_id = models.CharField(
    #     verbose_name='환경제어기 정보 ID',
    #     max_length=50
    # )
    oas_info = models.ForeignKey(
        'OasInfo',  # 참조할 모델 이름
        verbose_name='환경제어기 정보',
        on_delete=models.PROTECT, # 참조된 OasInfo 객체 삭제 시 이 OasGroup 객체는 보호됨
    )

    oas_name = models.CharField(
        verbose_name='환경제어기 이름',
        max_length=100,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        verbose_name='생성 날짜',
        auto_now_add=True # 객체 최초 생성 시 자동 저장
    )

    class Meta:
        verbose_name = '환경제어기 그룹 정보'
        verbose_name_plural = '환경제어기 그룹 정보'
        db_table = 'oas_group'

    def __str__(self):
        return self.oas_group_id


# OasInfo Model Definition (환경 제어기 정보)
class OasInfo(models.Model):
    # id 필드는 기본적으로 Django가 Primary Key로 자동 생성합니다.
    site = models.CharField(
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
    deviceId = models.CharField(
        verbose_name='환경 제어기 Device ID',
        max_length=50,
    )
    room = models.CharField(
        verbose_name='방 이름',
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
        verbose_name = '환경제어기 정보'
        verbose_name_plural = '환경제어기 정보'
        db_table = 'oas_info'
        # 지역 코드, 동, 호, site 조합은 고유해야 할 가능성이 높아 unique_together로 설정합니다.
        # unique_together = (('site', 'deviceId'),)

    def __str__(self):
        return f'{self.site}'