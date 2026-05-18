# 🚀 Project Roadmap & TODO

이 문서는 시스템 아키텍처 개선 및 남은 기능 구현 사항을 관리합니다.

## 🔴 Phase 1: 안정화 및 성능 최적화 (P0 - 긴급)
- [ ] **Redis 커넥션 풀 스트레스 테스트**
  - [ ] 500명 동시 접속 시 `connected_clients` 수치 모니터링
  - [ ] `cleanup_async_redis_pool` 동작 시 소켓 반환 속도 확인
- [ ] **TDengine 조회 성능 검증**
  - [ ] 100만 건 이상 데이터 조회 시 `sync_to_async` 스레드 풀 병목 여부 확인
  - [ ] 대용량 페이로드 JSON 직렬화 속도 최적화 (`ujson` 또는 `orjson` 도입 검토)
- [ ] **운영 환경(Production) 설정 자동화**
  - [ ] `DEBUG` 모드에 따른 Redis Cleanup 로직 분기 처리 (`if not settings.DEBUG: return`)

## 🟡 Phase 2: 기능 확장 및 연동 (P1 - 중요)
- [ ] **Flutter 앱 API 연동 테스트**
  - [ ] `DeviceRefreshView` 병렬 응답 데이터가 Flutter 차트 위젯에 정상 렌더링되는지 확인
  - [ ] 차트 데이터(480 포인트) 로딩 성능 측정
- [ ] **에러 핸들링 고도화**
  - [ ] Redis/TDengine 연결 실패 시 사용자에게 보여줄 친절한 에러 메시지 규격 정의
  - [ ] Sentry 또는 로그 파일에 상세 에러 스택 기록 (Traceback 포함)

## 🟢 Phase 3: 시스템 스케일링 (P2 - 중장기)
- [ ] **MQTT 브로커 모니터링 연동**
  - [ ] Mosquitto 브리지 상태를 Redis로 수집하여 대시보드에 표시
- [ ] **데이터 버퍼링 레이어 고도화**
  - [ ] 10만 에이전트 확장 대비 Redis Streams 데이터 만료 정책(Maxlen) 최적화
- [ ] **문서화 완료**
  - [ ] ADR-001(Async Architecture) 최종 승인 및 공유
  - [ ] Swagger(drf-spectacular)를 활용한 비동기 API 명세서 최적화