# your_app/mail_backends.py

from django.core.mail.backends.smtp import EmailBackend
from django.utils.functional import cached_property
import ssl
import smtplib

class CustomEmailBackend(EmailBackend):

    # local_hostname 오류 방지용 __init__ 유지
    def __init__(self, host=None, port=None, username=None, password=None,
                 use_tls=None, fail_silently=False, use_ssl=None,
                 timeout=None, ssl_keyfile=None, ssl_certfile=None,
                 local_hostname=None, **kwargs):
        super().__init__(host, port, username, password, use_tls,
                         fail_silently, use_ssl, timeout, ssl_keyfile,
                         ssl_certfile, local_hostname=local_hostname, **kwargs)

    # 💡 Handshake Failure 해결: SSL Context를 Django의 캐시 속성으로 재정의
    @cached_property
    def ssl_context(self):
        # 기본 context 생성
        context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=self.ssl_certfile
        )

        # 🔑 TLS 1.2 이상을 강제하여 Handshake Failure 오류 해결
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        if self.ssl_certfile and self.ssl_keyfile:
            context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)

        return context

    # open 메서드는 이제 재정의된 ssl_context 속성을 활용합니다.
    def open(self):
        if self.connection:
            return False

        try:
            # local_hostname 속성 접근 오류를 피하기 위해 getattr 사용
            local_hostname_value = getattr(self, 'local_hostname', None)

            # 2. EMAIL_USE_SSL = True (465 포트) 로직
            if self.use_ssl:
                # self.ssl_context 속성을 smtplib.SMTP_SSL에 전달합니다.
                print(f"self.host: {self.host}, self.port :{self.port} , local_hostname_value : {local_hostname_value}")
                self.connection = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    local_hostname=local_hostname_value,
                    timeout=self.timeout,
                    context=self.ssl_context, # <--- 재정의된 속성 사용
                )

            # 3. EMAIL_USE_TLS = True (587 포트) 로직
            elif self.use_tls or self.port == 587:
                self.connection = smtplib.SMTP(
                    self.host,
                    self.port,
                    local_hostname=local_hostname_value,
                    timeout=self.timeout
                )
                # starttls()에도 재정의된 context를 전달
                self.connection.starttls(context=self.ssl_context)

            else: # 일반 연결 (25 포트)
                self.connection = smtplib.SMTP(
                    self.host,
                    self.port,
                    local_hostname=local_hostname_value,
                    timeout=self.timeout
                )

            # 4. 로그인
            if self.username and self.password:
                print(f"self.username: {self.username}, self.password :{self.password} ")
                self.connection.login(self.username, self.password)

            return True

        except Exception as e:
            print(f"{e}")
            if not self.fail_silently:
                raise