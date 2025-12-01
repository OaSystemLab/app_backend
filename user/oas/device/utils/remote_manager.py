import requests
from django.conf import settings
import json
from rest_framework.exceptions import APIException
from rest_framework import status

# 외부 API 요청 실패 시 사용할 사용자 정의 예외 클래스
class ExternalAPIFailure(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = '외부 인증 API와의 통신에 실패했습니다.'
    default_code = 'external_api_failure'


class Bootup:
    """
    외부 환경 제어기 인증 API와 통신을 담당하는 매니저 클래스
    """

    # ⭐️ settings.py에서 불러온 토큰 사용
    # 토큰이 설정되지 않은 경우를 대비해 초기화 시점에 확인하는 것이 좋습니다.
    REMOTE_BACKEND_KEY = settings.REMOTE_BACKEND_KEY

    # Remote Backend 192.168.55.202:2000/api/bootup/compare/
    BASE_URL = "http://192.168.55.202:2000/api/bootup/compare/"

    @classmethod
    def check_request(cls, data: dict):
        """
        POST 요청으로 외부 API에 인증 데이터를 전송하고 응답을 받습니다.

        :param data: json 데이터 "dev_id" , "deviceId"
        :return: 외부 API에서 받은 응답 데이터 (dict)
        :raises ExternalAPIFailure: API 요청 실패, 타임아웃, 4xx/5xx 응답 시
        """

        if not cls.REMOTE_BACKEND_KEY:
            # 토큰이 없는 경우 (설정 오류)
            raise ExternalAPIFailure(detail="외부 API 토큰 설정이 누락되었습니다.")

        url = f"{cls.BASE_URL}" # bootup 비교

        print(f"DEBUG: 요청하려는 최종 URL: {url}")

        headers = {
            "Authorization": f"Bearer {cls.REMOTE_BACKEND_KEY}", # ⭐️ 저장된 토큰 사용
            "Content-Type": "application/json"
        }

        print("data : ", data)

        try:
            # POST 요청 및 5초 타임아웃 설정
            response = requests.post(
                url,
                data=json.dumps(data),
                #json=data,
                headers=headers,
                timeout=5
            )

            # 4xx 또는 5xx 응답 코드가 오면 예외 발생
            response.raise_for_status()

            # 성공적인 응답 (200대)의 JSON 데이터를 반환
            return response.json()


        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            response_text = e.response.text
            print(f"외부 API HTTP 에러 발생: {status_code}. 응답: {response_text}")
            # 다른 모든 HTTP 에러는 일반 ExternalAPIFailure로 처리
            raise ExternalAPIFailure(
                detail=f"외부 API 응답 오류 ({status_code}): {response_text[:100]}...",
                code='external_api_http_error'
            )
        except requests.exceptions.RequestException as e:
            # 연결 오류, 타임아웃, DNS 오류 등 요청 자체의 문제 발생 시
            print(f"외부 API 요청 실패: {e}")
            raise ExternalAPIFailure(detail=f"외부 API 연결 오류: {e}")
        except json.JSONDecodeError:
            # 응답은 받았으나 JSON 형식이 아닌 경우 (예: HTML 오류 페이지)
            print(f"외부 API 응답 JSON 디코딩 실패. 응답 내용: {response.text}")
            raise ExternalAPIFailure(detail="외부 API 응답 형식이 올바르지 않습니다.")