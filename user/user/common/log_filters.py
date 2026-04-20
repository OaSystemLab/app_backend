import logging
import threading

# 현재 요청 정보를 저장할 스레드 로컬 저장소
_thread_locals = threading.local()

class RequestMiddleware:
    """모든 요청을 스레드 로컬에 저장하는 미들웨어"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        return self.get_response(request)

class IPFilter(logging.Filter):
    """로그 레코드에 client_ip를 추가하는 필터"""
    def filter(self, record):
        request = getattr(_thread_locals, 'request', None)
        if request:
            # 프록시(Nginx 등) 뒤에 있을 경우를 대비해 IP 추출
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            record.client_ip = ip
        else:
            record.client_ip = '0.0.0.0'  # 요청이 없는 시스템 로그일 경우
        return True