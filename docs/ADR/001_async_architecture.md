# ADR 001: 대규모 동시 접속 처리를 위한 비동기(Async) 아키텍처 전환

## 1. 배경 (Context)
* 동시 접속 500명 이상의 환경에서 기존 동기식(Sync) 뷰와 DB/Redis 통신 시, 응답 대기(I/O Blocking)로 인한 병목 현상과 Gunicorn/Uvicorn 워커 고갈 문제가 예상됨.
* 실시간 대시보드 및 차트 조회 성능을 극대화하기 위해 핵심 API View와 Service 계층을 비동기(Async)로 전환하기로 결정함.

## 2. 결정 사항 (Decision)

### A. Redis 커넥션 풀 분리 (Two-Track 전략)
* **결정:** 동기용(`TD_REDIS_POOL`)과 비동기용(`TD_REDIS_ASYNC_POOL`) 커넥션 풀을 분리하여 운영한다.
* **이유:** 기존 Celery 등 백그라운드 작업의 안정성을 유지하면서, 비동기 뷰에서는 `asyncio.gather`를 통한 병렬 처리를 지원하기 위함.
* **이슈 해결:** Django `runserver` 환경에서 발생하는 "Event loop is closed" 에러 및 커넥션 누수(Zombie Connection)를 방지하기 위해, 이벤트 루프 딕셔너리 기반의 지연 생성(Lazy Initialization) 함수와 `cleanup_async_redis_pool()` 명시적 종료 로직을 적용함.

### B. TDengine 통신 비동기화 (`sync_to_async` 래퍼 사용)
* **결정:** TDengine REST API(`taosrest`) 드라이버를 교체하지 않고, Django의 `sync_to_async(thread_sensitive=False)`를 사용하여 백그라운드 스레드 풀로 위임한다.
* **이유:** TDengine의 공식 비동기 드라이버의 불안정성 리스크를 피하고, 이미 검증된 SQL 인젝션 방어(화이트리스트) 로직을 100% 재사용하기 위함. 메인 이벤트 루프의 블로킹 없이 수십만 건의 시계열 데이터를 조회할 수 있음.

### C. View 계층의 비동기 인증
* **결정:** DRF의 클래스 레벨 인증(`authentication_classes = []`)을 비활성화하고, 뷰 내부에서 `await get_authenticated_user(request)`를 직접 호출한다.
* **이유:** DRF의 기본 인증 로직이 동기식으로 동작하여 비동기 이벤트 루프를 블로킹(`SynchronousOnlyOperation`)하는 것을 방지하기 위함.

## 3. 결과 및 기대 효과 (Consequences)
* **성능:** I/O 대기 시간 동안 서버가 멈추지 않아 동시 처리량이 비약적으로 상승함.
* **안정성:** 개발 환경(`runserver`)과 운영 환경(Uvicorn/Gunicorn) 모두에서 에러 없이 동작하는 방탄 코드 베이스 확보.