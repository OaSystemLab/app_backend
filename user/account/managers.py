from django.contrib.auth.models import BaseUserManager

# UserInfo 모델을 생성하고 관리하는 커스텀 매니저
class UserInfoManager(BaseUserManager):
    """
    AbstractBaseUser를 사용할 때 필수적으로 정의해야 하는 커스텀 매니저입니다.
    사용자(UserInfo)와 슈퍼유저(create_superuser)를 생성하는 메서드를 포함합니다.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        슈퍼유저를 생성합니다. is_staff와 is_superuser를 True로 설정합니다.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)
