import asyncio
import redis
import redis.asyncio as async_redis
from django.conf import settings

redis_cfg = settings.TD_REDIS_CONFIG
# --- [1] 기존 동기(Sync) 연결 풀 ---
# Celery 작업이나 아직 동기 방식으로 남아있는 로직에서 사용합니다.
TD_REDIS_POOL = redis.ConnectionPool(
    host=redis_cfg['HOST'],
    port=redis_cfg['PORT'],
    password=redis_cfg['PASSWORD'],
    db=0,
    decode_responses=True,
    max_connections=200  # 동기 워커 수를 고려해 약간 증설
)

# --- [2] 🚀 신규 비동기(Async) 연결 풀 (대규모 API 통신용) ---
TD_REDIS_ASYNC_POOL = async_redis.ConnectionPool(
    host=redis_cfg['HOST'],
    port=redis_cfg['PORT'],
    password=redis_cfg['PASSWORD'],
    db=0,
    decode_responses=True,
    # 비동기는 연결을 쥐고 있는 시간이 극도로 짧아 더 많은 동시 연결을 효율적으로 처리합니다.
    max_connections=1000
)

# 🔴 비동기 풀은 전역 변수만 선언해두고, 값은 비워둡니다 (None).
_ASYNC_REDIS_POOLS = {}

def get_async_redis_pool():
    """
    현재 실행 중인 이벤트 루프를 확인하고,
    해당 루프에 맞는 커넥션 풀을 반환하거나 새로 생성합니다.
    """
    global _ASYNC_REDIS_POOLS

    # 현재 작동 중인 이벤트 루프를 가져옵니다.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 드물게 루프가 없는 경우 새로 생성 (방어 코드)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 1. 이미 파괴된(Closed) 옛날 루프들의 찌꺼기 풀을 메모리에서 청소합니다.
    dead_loops = [l for l in _ASYNC_REDIS_POOLS.keys() if l.is_closed()]
    for l in dead_loops:
        del _ASYNC_REDIS_POOLS[l]

    # 2. 현재 살아있는 루프용 풀이 없다면 새로 만들어 딕셔너리에 저장합니다.
    if loop not in _ASYNC_REDIS_POOLS:
        _ASYNC_REDIS_POOLS[loop] = async_redis.ConnectionPool(
            host=redis_cfg['HOST'],
            port=redis_cfg['PORT'],
            password=redis_cfg['PASSWORD'],
            db=0,
            decode_responses=True,
            max_connections=1000
        )

    return _ASYNC_REDIS_POOLS[loop]

async def cleanup_async_redis_pool():
    """
    현재 이벤트 루프에 할당된 Redis 커넥션 풀의 연결을 명시적으로 종료합니다.
    (좀비 커넥션 누수 방지용)
    """
    # 상용 환경(DEBUG=False)이고 Uvicorn을 쓴다면 연결을 끊지 않고 풀을 계속 유지합니다!
    if not settings.DEBUG:
        return

    global _ASYNC_REDIS_POOLS
    try:
        loop = asyncio.get_running_loop()
        if loop in _ASYNC_REDIS_POOLS:
            pool = _ASYNC_REDIS_POOLS[loop]
            # 🚀 [핵심] Redis 서버에 QUIT 신호를 보내 열려있는 소켓들을 안전하게 닫습니다.
            await pool.disconnect()

            # 파이썬 메모리에서도 제거
            del _ASYNC_REDIS_POOLS[loop]
    except Exception as e:
        pass