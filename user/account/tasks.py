
from celery import shared_task
from django.core.mail import send_mail # 실제 전송 함수 import
from django.conf import settings # 설정 정보 import

@shared_task
def send_auth_email_task(email, code):
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
    except Exception as e:
        # 전송 실패 시 처리
        print(f"이메일 전송 실패: {e}")
        return "이메일 전송 실패"