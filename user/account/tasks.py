
from celery import shared_task
from django.core.mail import send_mail # 실제 전송 함수 import
from django.conf import settings # 설정 정보 import
from .models import EmailLog


# bind=True, max_retries, default_retry_delay 설정 유지
@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def send_auth_email_task(self, email, code):
    """실제 이메일 전송 로직이 들어갈 자리입니다."""
    print(f"📧 이메일 전송 시뮬레이션: {email}에게 인증 코드 {code} 전송됨.")

    subject = "회원가입 이메일 인증 코드"
    message = f"인증 코드는 {code} 입니다. 5분 내에 입력해 주세요."
    html_message_template = """
    <html>
    <body>
        <h3 >이메일 인증</h3>

        <p>
            ℹ️ 인증번호 6자리 <strong>{code}</strong>
        <br>
        <p>
            위 6자리 번호를 입력하여 인증을 완료하세요.<br>
            <br>
            <strong>인증번호는 5분간 유효합니다.</strong>
        </p>
    </body>
    </html>
    """
    html_message = html_message_template.format(code=code)
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [email]

    try:
        send_mail(
            subject,
            message,
            from_email,
            recipient_list,
            fail_silently=False, # 전송 실패 시 예외 발생
            html_message=html_message,
        )
        return "이메일 전송 성공"
    except Exception as exc:
        # 이메일 전송 실패 시, Celery의 재시도 로직을 따릅니다.

        # 1. 재시도 횟수 초과 여부 확인
        if self.request.retries >= self.max_retries:
            # 2. 최종 실패 시 EmailLog에 기록
            error_msg = str(exc)

            EmailLog.objects.create(
                email=email,
                task_id=self.request.id, # 현재 Celery Task ID 기록
                log_type='FINAL_FAILURE',
                error_message=error_msg,
            )
            print(f"🚨 이메일 전송 최종 실패 및 로그 기록: {email} - {error_msg}")

            return "이메일 전송 최종 실패"

        else:
            # 3. 재시도 횟수가 남았으면 Celery에게 재시도를 요청합니다.
            print(f"⚠️ 이메일 전송 실패, 재시도 요청: {email} (현재 시도 {self.request.retries + 1}/{self.max_retries + 1})")
            raise self.retry(exc=exc)