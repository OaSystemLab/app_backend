import base64
import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from log_events.models import ProjectLogEntry # ⭐️ 통합 모델 임포트

# --- C++ 코드와 정확히 동일한 KEY와 IV를 사용해야 합니다! ---
# (C++ 코드의 예시: 32바이트 KEY, 16바이트 IV)

def decrypt_qr_data_cryptography(base64_data, user):
    """
    Base64 인코딩된 AES-256-CBC 데이터를 복호화하고 JSON으로 파싱합니다.
    (cryptography 라이브러리 사용)
    """

    KEY = b'keyoasa1b2c3d4e5f6g7h8i9j0k1l2m3'  # 32 bytes
    IV = b'ivoas1q2w3eqqqvs'    # 16 bytes

    try:
        # 1. Base64 디코딩
        encrypted_bytes = base64.b64decode(base64_data)

        # 2. 복호화 객체 생성 (AES-256-CBC)
        cipher = Cipher(
            algorithms.AES(KEY),
            modes.CBC(IV),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()

        # 3. 복호화
        decrypted_padded_bytes = decryptor.update(encrypted_bytes) + decryptor.finalize()

        # 4. PKCS7 패딩 제거
        # OpenSSL의 EVP 함수는 기본적으로 PKCS#7 패딩을 사용합니다.
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        decrypted_bytes = unpadder.update(decrypted_padded_bytes) + unpadder.finalize()

        # 5. UTF-8 JSON 문자열로 디코딩
        json_string = decrypted_bytes.decode('utf-8')

        # 6. JSON 객체로 파싱 및 반환
        json_object = json.loads(json_string)

        return json_object

    except base64.binascii.Error as e:
        # Base64 디코딩 실패 (잘못된 문자열 형식)
        print(f"복호화 오류: Base64 디코딩 실패. {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=user,
            level='ERROR',
            event_type='decrypt_qr_data_cryptography',
            message=f"복호화 오류: Base64 디코딩 실패.",
            request_data=f"{e}"
        )
        return None

    except ValueError as e:
        # 주로 패딩 제거 실패 시 발생 (잘못된 KEY, IV, 또는 암호문 변조)
        print(f"복호화 오류: 패딩 제거 실패 (KEY/IV 불일치 또는 데이터 변조 가능성). {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=user,
            level='ERROR',
            event_type='decrypt_qr_data_cryptography',
            message=f"복호화 오류: 패딩 제거 실패 (KEY/IV 불일치 또는 데이터 변조 가능성).",
            request_data=f"{e}"
        )
        return None

    except json.JSONDecodeError as e:
        # 복호화는 성공했으나, 결과 문자열이 JSON 형식이 아닌 경우
        print(f"복호화 오류: JSON 파싱 실패. {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=user,
            level='ERROR',
            event_type='decrypt_qr_data_cryptography',
            message=f"복호화 오류: JSON 파싱 실패.",
            request_data=f"{e}"
        )
        return None

    except Exception as e:
        # 위에 나열되지 않은 기타 예외
        print(f"복호화/파싱 중 알 수 없는 오류 발생: {type(e).__name__} - {e}")
        ProjectLogEntry.objects.create(
            app_name='oas.device',
            user=user,
            level='ERROR',
            event_type='decrypt_qr_data_cryptography',
            message=f"복호화/파싱 중 알 수 없는 오류 발생",
            request_data=f"{type(e).__name__} - {e}"
        )
        return None