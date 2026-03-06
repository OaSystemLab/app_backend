import requests
import time
import ssl
import json

import paho.mqtt.client as mqtt

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework import status
#from rest_framework.permissions import IsAuthenticated
from datetime import datetime


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



class AppMqttManager:
    """
    MQTT 요청 처리 하는 부분
    """
    def __init__(self):
        self.base_url = getattr(settings, 'REMOTE_BACKEND_URL', "").rstrip('/')
        self.api_key = getattr(settings, 'REMOTE_BACKEND_KEY', "")
        self.now = datetime.now()
        self.timeout = 5
        self.msg_data = None


    def __setData(self, server_info, data):
        #print("start setData")
        option_data = data.get('option', {})
        sleep_data = data.get('sleep', {})

        temp = {
            "jCAP" : "1.0",
            "sender" : {
                "type" : "cen_server",
                "info" : {
                    "ip"  : server_info['server_ip'] + ":" + server_info['server_port'],
                    "url" : '',
                    "name": '',
                }
            },
            "service" : {
                "init" : {
                    "time" : self.now.strftime('%Y.%m.%d.%H.%M.%S'),
                    "type" : "request",
                    "name" : "user_app",
                    "sequence" : "0",
                    "memo" : "user app requset",
                }
            },
            "request": {
                "type": data.get('type'),
                "action": data.get('action'),
                "option": {
                    "air": data.get('option', {}).get('air', ""),
                    "timer": option_data.get('timer', ""),
                    "reservation": option_data.get('reservation', []) # 오타 주의: reservation
                },
                "sleep" : {
                    "moodlampoff" : sleep_data.get('moodlampoff', ""),
                    "diallampoff" : sleep_data.get('diallampoff', ""),
                    "bedtime" : sleep_data.get('bedtime', ""),
                    "wakeuptime" : sleep_data.get('wakeuptime', ""),
                }
            }

        }


        self.msg_data = json.dumps(temp, ensure_ascii=False, indent="\t") + "0e"

        print(self.msg_data)


    def get_server_info(self, site_id):
        """
        특정 사이트의 MQTT 서버 정보를 원격지에서 가져옵니다.\
        {'server_ip': 'center.ventigen.co.kr', 'server_port': '8801', 'server_qos': '1', 'server_user': 'oasnode', 'server_pass': 'node!2qw'}
        """
        if not site_id:
            raise ValueError("site_id가 누락되었습니다.")

        endpoint = f"{self.base_url}/basic/v1/server-info/"
        params = {'site': site_id}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=self.timeout)

            # 4xx, 5xx 에러 발생 시 HTTPError 예외 발생
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            # 4xx 에러는 재시도해도 의미 없는 경우가 많음 (잘못된 요청)
            if 400 <= status_code < 500:
                print(f"클라이언트 오류 (재시도 안 함): {status_code}")
                raise ValueError(f"Invalid request: {status_code}")
            # 5xx 에러는 서버 일시 오류이므로 재시도 대상
            raise e
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"네트워크 일시 오류: {e}")
            raise e # Celery가 이 예외를 받고 재시도함

    def broker_publish(self, data):
        sitecode = data['sitecode']
        site, dong, ho, id = sitecode[:8], sitecode[8:12], sitecode[12:16], sitecode[16:17]
        topic = f"CEN_SERVER/OASISS/{site}/controller/{dong}/{ho}/{id}"


        print(f"test :{topic}")
        # 1. 서버 정보 가져오기 및 데이터 세팅
        server_info = self.get_server_info(site)
        self.__setData(server_info, data)

        # 2. 내부 NAT IP 맵핑 로직
        server_url = f"{server_info['server_ip']}:{server_info['server_port']}"
        mapping = {
            "center.ventigen.co.kr:8801": "10.10.10.20",
            "center.ventigen.co.kr:8800": "10.10.10.10",
            "192.168.55.201:8800": "192.168.55.201"
        }
        server_ip = mapping.get(server_url, server_info['server_ip'])

        # 3. MQTT 클라이언트 설정 및 전송
        # Paho-MQTT 2.x API 버전 명시 (2026년 기준 표준)
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations("/oasiss/conf/ssl/ca/ca.crt")
            context.load_cert_chain("/oasiss/conf/ssl/client/client.crt", "/oasiss/conf/ssl/client/client.key")

            client.tls_set_context(context)
            client.tls_insecure_set(True)
            client.username_pw_set(server_info['server_user'], server_info['server_pass'])

            client.connect(server_ip, int(server_info['server_port']), 60)

            #client.loop_start()
            #time.sleep(1)

            # 전송 시작
            publish_result = client.publish(topic, self.msg_data, qos=1)

            # [가장 중요] 전송이 완료될 때까지 최대 5초 대기
            # 이 코드가 없으면 데이터 전송 전에 disconnect가 실행되어 Protocol Error가 발생합니다.
            publish_result.wait_for_publish(timeout=5)

            return True
        except Exception as e:
            print(f"MQTT Publish Error: {e}")
            raise e # Celery Retry를 위해 예외를 밖으로 던집니다.
        finally:
            #client.loop_stop()
            client.disconnect()