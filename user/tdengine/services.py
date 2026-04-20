import taos
import redis
import json
import time

import redis.asyncio as async_redis
from redis.exceptions import ConnectionError, TimeoutError, AuthenticationError
import taosrest
from datetime import datetime
from django.conf import settings

from .redis_pool import TD_REDIS_POOL, TD_REDIS_ASYNC_POOL, get_async_redis_pool
# Default setting.
import logging
# logger 객체 생성 (__name__을 넣으면 현재 모듈 이름으로 로거가 설정됩니다)
logger = logging.getLogger(__name__)
# LOG
# DEBUG: 개발 중에만 필요한 상세 정보
# INFO: 정상적인 동작 흐름 확인
# WARNING: 잠재적 문제
# ERROR: 실제 오류 발생


class TDengineService:
    # 요청하신 36개 컬럼 리스트
    MONITORING_COLUMNS = [
        'ts', 'sensor_data_nest_score', 'sensor_data_air_score', 'sensor_data_oxy',
        'sensor_data_o2row', 'sensor_data_co2', 'sensor_data_tvoc',
        'sensor_data_dust_10', 'sensor_data_dust_25', 'sensor_data_temp',
        'sensor_data_humi', 'grade_airquality', 'grade_comfortable',
        'sensor_score_oxy', 'sensor_score_co2', 'sensor_score_tvoc' ,'sensor_score_dust10',
        'sensor_score_dust25', 'sensor_score_temp','sensor_score_humi',
        'grade_temperature', 'grade_humidity', 'grade_tvoc', 'grade_co2',
        'grade_o2', 'grade_pm10', 'grade_pm2_5', 'progress_value_airquality',
        'progress_value_comfortable', 'progress_value_temperature',
        'progress_value_humidity', 'progress_value_tvoc', 'progress_value_co2',
        'progress_value_o2', 'progress_value_pm10', 'progress_value_pm2_5',
        'dev_status_envi_manage', 'dev_status_occu_state', 'dev_status_mode_state',
        'dev_status_oxy_state', 'dev_status_vent_state', 'dev_status_vent_conf','dev_status_led_state',
        'dev_status_rout_num',
        'reservation',
        'dev_status_lcd_state','dev_sleep_enable', 'dev_sleep_moodlamp' ,'dev_sleep_diallamp', 'dev_sleep_bed_time', 'dev_sleep_wake_up_time'
    ]
    # 조회를 허용할 테이블 목록
    ALLOWED_TABLES = {'st_dev_sensing', 'st_dev_hour_avg', 'st_dev_day_night_avg'}

    @staticmethod
    def get_client():
        cfg = settings.TDENGINE_CONFIG
        # return taosrest.connect(
        #     host=cfg['HOST'], user=cfg['USER'],
        #     password=cfg['PASSWORD'], database=cfg['DB']
        # )
        return taosrest.connect(
            url=f"http://{cfg['HOST']}:6041",
            user=cfg['USER'],
            password=cfg['PASSWORD'],
            database=cfg['DB'],
            timeout=5
        )


    def get_latest_data(self, sitecode):
        conn = self.get_client()
        cursor = conn.cursor()
        try:
            # SQL에서 별칭(Alias)을 사용하여 컬럼명을 즉시 매핑
            select_clause = ", ".join([f"LAST_ROW({col}) AS {col}" for col in self.MONITORING_COLUMNS])
            query = f"SELECT {select_clause} FROM st_dev_sensing WHERE sitecode = '{sitecode}'"

            cursor.execute(query)
            row = cursor.fetchone()

            #print(f"DEBUG> row {row}")

            if row:
                # 데이터를 딕셔너리로 결합
                data = dict(zip(self.MONITORING_COLUMNS, row))

                # JSON 전송을 위해 datetime만 문자열로 변환 (수치 데이터는 그대로 유지)
                for key, value in data.items():
                    if isinstance(value, datetime):
                        data[key] = value.isoformat()

                #print(f"DEBUG> {data}")
                return data
            return None
        finally:
            cursor.close()
            conn.close()

    def get_history_data(self, sitecode, select_clause, start_time, end_time):
        """
        start_time/end_time 형식: '2026-02-05 00:00:00'
        """
        conn = self.get_client()
        cursor = conn.cursor()
        try:
            query = (
                f"SELECT ts, {select_clause} FROM st_dev_sensing "
                f"WHERE sitecode = '{sitecode}' "
                f"AND ts >= '{start_time}' AND ts <= '{end_time}' "
                f"ORDER BY ts DESC " # 최신순 정렬
                f"LIMIT 10000"
            )

            cursor.execute(query)
            rows = cursor.fetchall()

            # result_list = []
            # for row in rows:
            #     data = dict(zip(self.MONITORING_COLUMNS, row))
            #     # datetime 변환 로직 적용 (생략)
            #     result_list.append(data)

            return rows
        finally:
            cursor.close()
            conn.close()
    # ---------------------------------------------------------------------------------- #
    # 2026-04-17 get_dashboard_async 완료 되면 삭제
    def _execute_sensor_query_b(self, table_name, sitecode, select_clause, start_time, end_time):
        # 1. 테이블 이름 검증
        if table_name not in self.ALLOWED_TABLES:
            raise ValueError(f"Invalid table access: {table_name}")

        # 2. 컬럼 유효성 검사 (SQL Injection 방지)
        # 문자열로 들어온 컬럼들을 분리 (예: "sensor_data_co2, sensor_data_temp")
        requested_cols = [col.strip() for col in select_clause.split(',') if col.strip()]

        # MONITORING_COLUMNS 세트로 변환 (조회 성능 최적화)
        valid_column_set = set(self.MONITORING_COLUMNS)

        clean_cols = []
        for col in requested_cols:
            if col in valid_column_set:
                clean_cols.append(col)
            else:
                # 리스트에 없는 컬럼이 요청되면 보안 위험으로 간주하고 차단
                raise ValueError(f"Security Warning: Unregistered column '{col}' requested.")

        # 검증된 컬럼이 하나도 없으면 에러 (ts는 기본으로 조회하므로 선택사항)
        if not clean_cols:
             safe_select_str = ""
        else:
             safe_select_str = ", " + ", ".join(clean_cols)

        # 3. 쿼리 실행
        conn = self.get_client()
        cursor = conn.cursor()
        try:
            query = (
                f"SELECT ts, {select_clause} FROM {table_name} "
                f"WHERE sitecode = '{sitecode}' "
                f"AND ts >= '{start_time}' AND ts <= '{end_time}' "
                f"ORDER BY ts DESC " # 최신순 정렬
                f"LIMIT 1000000"
            )

            cursor.execute(query)
            rows = cursor.fetchall()

            return rows

        finally:
            cursor.close()
            conn.close()

    def _execute_sensor_query(self, table_name, sitecode, select_list, start_time, end_time):
        # 1. 테이블 이름 검증 (화이트리스트)
        if table_name not in self.ALLOWED_TABLES:
            raise ValueError(f"Invalid table access: {table_name}")

        # 2. 컬럼 유효성 검사 (SQL Injection 방지 핵심)
        valid_column_set = set(self.MONITORING_COLUMNS)
        clean_cols = [col.strip() for col in select_list if col.strip() in valid_column_set]

        if not clean_cols:
            # 요청된 컬럼이 모두 유효하지 않을 경우 보안상 빈 값을 반환하거나 에러 발생
            raise ValueError("Security Warning: 유효하지 않은 컬럼 요청입니다.")

        # 검증된 컬럼들로만 구성된 안전한 문자열 생성
        safe_select_str = ", ".join(clean_cols)

        conn = self.get_client()
        cursor = conn.cursor()
        try:
            # serivalzer 에서
            query = (
                f"SELECT ts, {safe_select_str} FROM {table_name} "
                f"WHERE sitecode = '{sitecode}' "
                f"AND ts >= '{start_time}' AND ts <= '{end_time}' "
                f"ORDER BY ts DESC " # 최신순 정렬
                f"LIMIT 1000000"
            )

            cursor.execute(query)

            return cursor.fetchall()

        finally:
            cursor.close()
            conn.close()


    # 공개 메서드들
    def get_history_data(self, sitecode, select_clause, start_time, end_time):
        return self._execute_sensor_query(
            "st_dev_sensing", sitecode, select_clause, start_time, end_time
        )

    def get_hourly_data(self, sitecode, select_clause, start_time, end_time):
        return self._execute_sensor_query(
            "st_dev_hour_avg", sitecode, select_clause, start_time, end_time
            #"st_senser_hourly", sitecode, select_clause, start_time, end_time
        )
    def get_day_night_data(self, sitecode, select_clause, start_time, end_time):
        return self._execute_sensor_query(
            "st_dev_day_night_avg", sitecode, select_clause, start_time, end_time
        )
    # ---------------------------------------------------------------------------------- #

# 전역 인스턴스 생성 (다른 앱에서 import 하여 사용)
td_service = TDengineService()


class DashboardService:
    """
    환경제어기 대시보드의 실시간 상태(하트비트) 및 최신 센싱 데이터를 처리하는 서비스 클래스입니다.

    대규모 트래픽(동시 접속 500명 이상) 환경에서 기존 동기식 로직의 안정성과
    새로운 비동기 API의 고성능 논블로킹(Non-blocking) 처리를 모두 만족시키기 위해,
    Redis 커넥션 풀(Connection Pool)을 투 트랙(Two-track)으로 운영합니다.

    Attributes:
        r_conn (redis.Redis):
            Celery 백그라운드 작업 등 기존 동기(Sync) 로직에서 안전하게 사용하는 Redis 연결 객체입니다.
        async_r_conn (redis.asyncio.Redis):
            API 뷰에서 대량의 장비 데이터를 병렬(asyncio.gather)로 수집할 때,
            이벤트 루프 대기열 병목을 방지하기 위해 사용하는 비동기(Async) Redis 연결 객체입니다.
    """
    def __init__(self):
        """
        DashboardService 인스턴스를 초기화하며, 설정된 글로벌 커넥션 풀을 참조하여
        동기 및 비동기 Redis 통신용 객체를 각각 할당합니다.
        """
        # 1. 기존 동기 함수용 커넥션
        self.r_conn = redis.Redis(connection_pool=TD_REDIS_POOL)
        # 2. 신규 비동기 함수용 커넥션
        self.async_r_conn = async_redis.Redis(connection_pool=TD_REDIS_ASYNC_POOL)
    # ---------------------------------------------------------------------------------- #
    # 2026-04-17 get_dashboard_async 완료 되면 삭제
    def _tdredis_execute(self, v_data, keyname:str):

        # 1. 연결 객체 생성
        conn = self.r_conn

        # 연결에 실패하여 None이 반환된 경우 처리 (app 에는 없는 것으로 처리함.)
        if conn is None:
            return {}

        # 2. 조회할 키 생성
        match keyname:
            case "userapp_analysis":
                key = f"userapp_analysis:{v_data['sitecode'][:-1]}"
            case "userapp_dashboard" :
                key = f"userapp_dashboard:{v_data['sitecode']}"

        try:
            # 3. 데이터 가져오기 (가장 일반적인 GET 방식 예시)
            result = conn.get(key)

            if result:
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
                    return result

            else:
                logger.warning(f"No data found for key: {key}")
                return {}

        except redis.RedisError as e:
            logger.error(f"Redis Error: {e}", exc_info=True)
            return {}
        finally:
            # 연결 풀을 사용하므로 명시적인 close는 상황에 따라 생략 가능하지만,
            # 안전한 자원 관리를 위해 기술합니다.
            conn.close()
    # 공개 메서드들
    def get_dashboard(self, v_data):
        match v_data['data_type']:
            case "a1":
                return self._tdredis_execute(v_data, "userapp_analysis")
            case "a2":
                return self._tdredis_execute(v_data, "userapp_analysis")
            case "a3":
                return self._tdredis_execute(v_data, "userapp_dashboard")
    # ---------------------------------------------------------------------------------- #

    async def _tdredis_execute_async(self, v_data, keyname: str):
        """내부 비동기 Redis 조회 헬퍼 메서드"""

        # 1. 🚀 [핵심] 살아있는 이벤트 루프에서 안전한 비동기 풀을 가져옵니다.
        conn = async_redis.Redis(connection_pool=get_async_redis_pool())

        # 2. 조회할 키 생성
        match keyname:
            case "userapp_analysis":
                key = f"userapp_analysis:{v_data['sitecode'][:-1]}"
            case "userapp_dashboard":
                key = f"userapp_dashboard:{v_data['sitecode']}"
            case _:
                return {}

        try:
            # 3. 데이터 가져오기 (await 적용)
            result = await conn.get(key)

            if result:
                try:
                    # redis.asyncio는 기본적으로 bytes 또는 str을 반환합니다.
                    return json.loads(result)
                except json.JSONDecodeError:
                    return result
            else:
                logger.warning(f"No data found for key: {key}")
                return {}

        except async_redis.RedisError as e: # 비동기 예외 클래스로 변경
            logger.error(f"Async Redis Error: {e}", exc_info=True)
            return {}
    # ---------------------------------------------------------
    # 공개(Public) 비동기 메서드
    # ---------------------------------------------------------
    async def get_dashboard_async(self, v_data):
        match v_data['data_type']:
            case "a1" | "a2":
                return await self._tdredis_execute_async(v_data, "userapp_analysis")
            case "a3":
                return await self._tdredis_execute_async(v_data, "userapp_dashboard")
            case _:
                return None



    def get_heartbeat_status(self, sitecode):
        """
        Redis ZSET(heartbeat:index)만 조회하여 장비의 통신 상태를 반환합니다.
        """
        redis_conn = self.r_conn
        now = time.time()

        # 2. Redis ZSET에서 마지막 통신 시간(Score)만 조회
        last_ts = redis_conn.zscore("heartbeat:index", sitecode)

        # 데이터가 아예 없는 경우 처리
        if last_ts is None:
            return None,None,None

        # 3. 상태 판별 및 리턴 값 계산
        diff_seconds = int(now - last_ts)
        last_seen = datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')

        # 상태 결정 로직
        if diff_seconds <= 3600:
            status = "normal"
            tstring = "정상"  # 1시간 이내 데이터 수신 시
        elif diff_seconds <= 21600:
            # 1시간(3600초) < diff_seconds <= 6시간(21600초) 사이일 때
            status = "warning"
            tstring = "1시간 이상 로그 안옴"
        elif diff_seconds <= 86400:
            # 6시간(21600초) < diff_seconds <= 24시간(86400초) 사이일 때
            status = "warning"
            tstring = "6시간 이상 로그 안옴"
        else:
            # 24시간(86400초)을 초과한 모든 경우
            status = "critical"
            tstring = "24시간 이상 로그 안옴"

        return status,  tstring ,last_seen


    async def get_heartbeat_status_async(self, sitecode):
        """
        Redis ZSET(heartbeat:index)만 조회하여 장비의 통신 상태를 비동기로 반환합니다.
        """
        conn = async_redis.Redis(connection_pool=get_async_redis_pool())

        now = time.time()

        # ⚡️ [핵심 포인트] I/O 작업인 Redis 호출 시 워커가 멈추지 않도록 await를 사용합니다.
        # 주의: 이 코드가 작동하려면 self.r_conn이 'redis.asyncio'로 생성된 클라이언트여야 합니다.
        last_ts = await conn.zscore("heartbeat:index", sitecode)

        # 데이터가 아예 없는 경우 처리
        if last_ts is None:
            return None, None, None

        # 상태 판별 및 리턴 값 계산
        diff_seconds = int(now - last_ts)
        last_seen = datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')

        # 분기문을 간결하게 정리
        if diff_seconds <= 3600:
            status, tstring = "normal", "정상"
        elif diff_seconds <= 21600:
            status, tstring = "warning", "1시간 이상 로그 안옴"
        elif diff_seconds <= 86400:
            status, tstring = "warning", "6시간 이상 로그 안옴"
        else:
            status, tstring = "critical", "24시간 이상 로그 안옴"

        return status, tstring, last_seen

    def redis_get_sensing(self, sitecode):

        # 1. 연결 객체 생성
        conn = self.r_conn

        # 연결에 실패하여 None이 반환된 경우 처리 (app 에는 없는 것으로 처리함.)
        if conn is None:
            return {}

        # 2. 조회할 키 생성
        key = f"dev_sensing:{sitecode}"

        jdata = {}
        data = {}

        try:
            # 3. 데이터 가져오기 (가장 일반적인 GET 방식 예시)
            result = conn.get(key)

            if result:
                try:
                    jdata = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    jdata = result

                # 1. 최상위 리스트 안전하게 추출
                dev_data_list = jdata.get('service', {}).get('dev_data', [])
                if not dev_data_list:
                    logger.warning("⚠️ dev_data 리스트가 비어 있습니다.")
                    return {}

                # 첫 번째 항목 선택
                item = dev_data_list[0]

                # 2. 하위 섹션별로 변수 분리 (데이터가 없으면 빈 딕셔너리 {} 반환)
                s_data  = item.get('sensor_data', {})
                s_score = item.get('sensor_score', {})
                grade   = item.get('grade', {})
                prog    = item.get('progressValue', {})
                status  = item.get('dev_status', {})
                sleep   = item.get('dev_sleep', {})

                # 3. 시간 변환 (raw_time이 없을 경우를 대비해 현재 시간 또는 기본값 설정)
                raw_time = item.get('time_stemp')
                try:
                    dt_obj = datetime.strptime(raw_time, "%Y.%m.%d.%H.%M.%S")
                    ts_formatted = dt_obj.strftime("%Y-%m-%dT%H:%M:%S")
                except (ValueError, TypeError):
                    ts_formatted = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                # 4. 데이터 조립 (안전한 호출)
                data = {
                    'ts': ts_formatted,

                    # Sensor Data (Float)
                    "sensor_data_nest_score": float(s_data.get('nest_score', 0)),
                    "sensor_data_air_score":  float(s_data.get('air_score', 0)),
                    "sensor_data_oxy":        float(s_data.get('oxy', 0)),
                    "sensor_data_o2row":      float(s_data.get('o2Row', 0)),
                    "sensor_data_co2":        float(s_data.get('co2', 0)),
                    "sensor_data_tvoc":       float(s_data.get('tvoc', 0)),
                    "sensor_data_dust_10":    float(s_data.get('dust_10', 0)),
                    "sensor_data_dust_25":    float(s_data.get('dust_25', 0)),
                    "sensor_data_temp":       float(s_data.get('temp', 0)),
                    "sensor_data_humi":       float(s_data.get('humi', 0)),

                    # Sensor Score (Int)
                    "sensor_score_oxy":    int(s_score.get('oxy', 0)),
                    "sensor_score_co2":    int(s_score.get('co2', 0)),
                    "sensor_score_tvoc":   int(s_score.get('tvoc', 0)),
                    "sensor_score_dust10": int(s_score.get('dust_10', 0)),
                    "sensor_score_dust25": int(s_score.get('dust_25', 0)),
                    "sensor_score_temp":   int(s_score.get('temp', 0)),
                    "sensor_score_humi":   int(s_score.get('humi', 0)),

                    # Grade (Int)
                    "grade_airquality":  int(grade.get('airQuality', 0)),
                    "grade_comfortable": int(grade.get('comfortable', 0)),
                    "grade_temperature": int(grade.get('temperature', 0)),
                    "grade_humidity":    int(grade.get('humidity', 0)),
                    "grade_tvoc":        int(grade.get('tvoc', 0)),
                    "grade_co2":         int(grade.get('co2', 0)),
                    "grade_o2":          int(grade.get('o2', 0)),
                    "grade_pm10":        int(grade.get('pm10', 0)),
                    "grade_pm2_5":       int(grade.get('pm2_5', 0)),

                    # Progress Value (Int)
                    "progress_value_airquality":  int(prog.get('airQuality', 0)),
                    "progress_value_comfortable": int(prog.get('comfortable', 0)),
                    "progress_value_temperature": int(prog.get('temperature', 0)),
                    "progress_value_humidity":    int(prog.get('humidity', 0)),
                    "progress_value_tvoc":        int(prog.get('tvoc', 0)),
                    "progress_value_co2":         int(prog.get('co2', 0)),
                    "progress_value_o2":          int(prog.get('o2', 0)),
                    "progress_value_pm10":        int(prog.get('pm10', 0)),
                    "progress_value_pm2_5":       int(prog.get('pm2_5', 0)),

                    # Device Status (String)
                    "dev_status_envi_manage": status.get('envi_manage', ''),
                    "dev_status_occu_state":  status.get('occu_state', ''),
                    "dev_status_mode_state":  status.get('mode_state', ''),
                    "dev_status_oxy_state":   status.get('oxy_state', ''),
                    "dev_status_vent_state":  status.get('vent_state', ''),
                    "dev_status_vent_conf":   status.get('vent_conf', ''),
                    "dev_status_led_state":   status.get('led_state', ''),
                    "dev_status_rout_num":    status.get('rout_num', ''),
                    "reservation":            status.get('reservation', ''),
                    "dev_status_lcd_state":   status.get('lcd_state', ''),

                    # Sleep Status (String)
                    "dev_sleep_enable":       sleep.get('enable', ''),
                    "dev_sleep_moodlamp":     sleep.get('moodlamp', ''),
                    "dev_sleep_diallamp":     sleep.get('diallamp', ''),
                    "dev_sleep_bed_time":     sleep.get('bed_time', ''),
                    "dev_sleep_wake_up_time": sleep.get('wake_up_time', '')
                }
                #logger.info(f"성공적으로 정제된 데이터: {data}")
                return data

            else:
                logger.warning(f"No data found for key: {key}")
                return  jdata

        except redis.RedisError as e:
            logger.error(f"Redis Error: {e}", exc_info=True)
            return data
        finally:
            # 연결 풀을 사용하므로 명시적인 close는 상황에 따라 생략 가능하지만,
            # 안전한 자원 관리를 위해 기술합니다.
            conn.close()


    async def redis_get_sensing_async(self, sitecode):
        """
        비동기 Redis 풀을 사용하여 장비의 센싱 데이터를 가져오고 파싱합니다.
        """
        # 1. 비동기 연결 객체 사용
        # (앞서 투 트랙 전략에서 추가한 self.async_r_conn을 사용합니다.)
        #conn = getattr(self, 'async_r_conn', None)
        conn = async_redis.Redis(connection_pool=get_async_redis_pool())

        if conn is None:
            logger.error("async_r_conn is not initialized.")
            return {}

        key = f"dev_sensing:{sitecode}"
        jdata = {}
        data = {}

        try:
            # 2. 🚀 [핵심] await를 사용하여 비동기적으로 데이터를 가져옵니다.
            result = await conn.get(key)

            if result:
                try:
                    # redis.asyncio는 기본적으로 문자열 또는 bytes를 반환합니다.
                    jdata = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    jdata = result

                # 1. 최상위 리스트 안전하게 추출
                dev_data_list = jdata.get('service', {}).get('dev_data', [])
                if not dev_data_list:
                    logger.warning(f"⚠️ dev_data 리스트가 비어 있습니다. Key: {key}")
                    return {}

                # 첫 번째 항목 선택
                item = dev_data_list[0]

                # 2. 하위 섹션별로 변수 분리
                s_data  = item.get('sensor_data', {})
                s_score = item.get('sensor_score', {})
                grade   = item.get('grade', {})
                prog    = item.get('progressValue', {})
                status  = item.get('dev_status', {})
                sleep   = item.get('dev_sleep', {})

                # 3. 시간 변환
                raw_time = item.get('time_stemp')
                try:
                    dt_obj = datetime.strptime(raw_time, "%Y.%m.%d.%H.%M.%S")
                    ts_formatted = dt_obj.strftime("%Y-%m-%dT%H:%M:%S")
                except (ValueError, TypeError):
                    ts_formatted = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                # 4. 데이터 조립 (CPU 연산이므로 await 불필요)
                data = {
                    'ts': ts_formatted,

                    # Sensor Data (Float)
                    "sensor_data_nest_score": float(s_data.get('nest_score', 0)),
                    "sensor_data_air_score":  float(s_data.get('air_score', 0)),
                    "sensor_data_oxy":        float(s_data.get('oxy', 0)),
                    "sensor_data_o2row":      float(s_data.get('o2Row', 0)),
                    "sensor_data_co2":        float(s_data.get('co2', 0)),
                    "sensor_data_tvoc":       float(s_data.get('tvoc', 0)),
                    "sensor_data_dust_10":    float(s_data.get('dust_10', 0)),
                    "sensor_data_dust_25":    float(s_data.get('dust_25', 0)),
                    "sensor_data_temp":       float(s_data.get('temp', 0)),
                    "sensor_data_humi":       float(s_data.get('humi', 0)),

                    # Sensor Score (Int)
                    "sensor_score_oxy":    int(s_score.get('oxy', 0)),
                    "sensor_score_co2":    int(s_score.get('co2', 0)),
                    "sensor_score_tvoc":   int(s_score.get('tvoc', 0)),
                    "sensor_score_dust10": int(s_score.get('dust_10', 0)),
                    "sensor_score_dust25": int(s_score.get('dust_25', 0)),
                    "sensor_score_temp":   int(s_score.get('temp', 0)),
                    "sensor_score_humi":   int(s_score.get('humi', 0)),

                    # Grade (Int)
                    "grade_airquality":  int(grade.get('airQuality', 0)),
                    "grade_comfortable": int(grade.get('comfortable', 0)),
                    "grade_temperature": int(grade.get('temperature', 0)),
                    "grade_humidity":    int(grade.get('humidity', 0)),
                    "grade_tvoc":        int(grade.get('tvoc', 0)),
                    "grade_co2":         int(grade.get('co2', 0)),
                    "grade_o2":          int(grade.get('o2', 0)),
                    "grade_pm10":        int(grade.get('pm10', 0)),
                    "grade_pm2_5":       int(grade.get('pm2_5', 0)),

                    # Progress Value (Int)
                    "progress_value_airquality":  int(prog.get('airQuality', 0)),
                    "progress_value_comfortable": int(prog.get('comfortable', 0)),
                    "progress_value_temperature": int(prog.get('temperature', 0)),
                    "progress_value_humidity":    int(prog.get('humidity', 0)),
                    "progress_value_tvoc":        int(prog.get('tvoc', 0)),
                    "progress_value_co2":         int(prog.get('co2', 0)),
                    "progress_value_o2":          int(prog.get('o2', 0)),
                    "progress_value_pm10":        int(prog.get('pm10', 0)),
                    "progress_value_pm2_5":       int(prog.get('pm2_5', 0)),

                    # Device Status (String)
                    "dev_status_envi_manage": status.get('envi_manage', ''),
                    "dev_status_occu_state":  status.get('occu_state', ''),
                    "dev_status_mode_state":  status.get('mode_state', ''),
                    "dev_status_oxy_state":   status.get('oxy_state', ''),
                    "dev_status_vent_state":  status.get('vent_state', ''),
                    "dev_status_vent_conf":   status.get('vent_conf', ''),
                    "dev_status_led_state":   status.get('led_state', ''),
                    "dev_status_rout_num":    status.get('rout_num', ''),
                    "reservation":            status.get('reservation', ''),
                    "dev_status_lcd_state":   status.get('lcd_state', ''),

                    # Sleep Status (String)
                    "dev_sleep_enable":       sleep.get('enable', ''),
                    "dev_sleep_moodlamp":     sleep.get('moodlamp', ''),
                    "dev_sleep_diallamp":     sleep.get('diallamp', ''),
                    "dev_sleep_bed_time":     sleep.get('bed_time', ''),
                    "dev_sleep_wake_up_time": sleep.get('wake_up_time', '')
                }
                return data

            else:
                logger.warning(f"No data found for key: {key}")
                return jdata

        # redis.asyncio.RedisError를 잡기 위해 수정됨
        except async_redis.RedisError as e:
            logger.error(f"Async Redis Error: {e}", exc_info=True)
            return data


db_service = DashboardService()



class ChartService:
    """
    환경제어기 센서의 시계열 차트 데이터를 Redis Stream에서 조회하고 가공하는 서비스 클래스입니다.

    대규모 데이터(수백 개의 차트 포인트) 조회 시 매번 새로운 통신 연결을 맺고 끊는 오버헤드를
    방지하기 위해, 사전에 정의된 커넥션 풀(Connection Pool)을 재사용하여 성능을 최적화합니다.
    """
    def __init__(self):
        """
        ChartService 인스턴스를 초기화하며 데이터베이스(Redis) 통신용 커넥션 객체를 할당합니다.

        기존의 동기식 작업(Celery 등)과 대규모 동시 접속을 처리하기 위한 비동기(Async) APIView
        환경 모두를 안전하게 지원하기 위해, 용도에 맞는 커넥션 풀을 투 트랙(Two-track)으로 분리하여 매핑합니다.
        """
        # 1. 동기(Sync) 연결: 기존 Celery 작업이나 동기식 뷰에서 안전하게 사용하기 위한 커넥션 풀
        self.r_conn = redis.Redis(connection_pool=TD_REDIS_POOL)

        # 2. 비동기(Async) 연결: 동시 접속 500명 환경의 차트 조회를 블로킹 없이 처리하기 위한 커넥션 풀
        # (비동기 뷰에서 await self.async_r_conn.xrevrange(...) 형태로 사용됩니다)
        #self.async_r_conn = async_redis.Redis(connection_pool=TD_REDIS_ASYNC_POOL)
    #@staticmethod
    def get_sensor_chart_data(self, sitecode: str, data_type: str):
        # 1. Redis 연결 (Go에서 설정한 DB 번호와 일치해야 함)
        conn = self.r_conn

        # 2. Redis Stream Key 생성 (Go 소스와 동일한 규칙)
        stream_key = f"dev_sensor:{sitecode}:{data_type}"

        # 3. Stream 데이터 조회 (XRANGE: 전체 데이터 가져오기)
        # 만약 최신순으로 가져오고 싶다면 xrevrange를 사용하세요.
        raw_data = conn.xrevrange(stream_key, min='-', max='+', count=480)

        # user app 에서 파서 해서 처리 하는 방식으로 변경
        # chart_data = []
        # for entry in raw_data:
        #     # entry 구조: (b'1713072600000-0', {b'ts': b'1713072600', b'val': b'450.50'})
        #     _, values = entry

        #     # Redis는 데이터를 bytes로 반환하므로 decode 및 형변환 필요
        #     ts = int(values.get('ts', 0))
        #     val = float(values.get('val', 0.0))


        #     # 앱(Flutter)에서 바로 쓸 수 있게 [ts, val] 형태로 구성
        #     chart_data.append([ts, val])

        return raw_data
    # 2026-04-16 비동기 방식으로 적용
    async def get_sensor_chart_data_async(self, sitecode: str, data_type: str):
        """
        Redis Stream 데이터를 비동기로 조회하여 정제된 리스트로 반환합니다.
        """
        #conn = self.async_r_conn
        conn = async_redis.Redis(connection_pool=get_async_redis_pool())
        stream_key = f"dev_sensor:{sitecode}:{data_type}"

        try:
            # 🚀 [핵심] await를 사용하여 비동기로 조회 (최신 데이터 480개)
            raw_data = await conn.xrevrange(stream_key, min='-', max='+', count=480)

            return raw_data

        except Exception as e:
            logger.error(f"Error fetching chart data: {str(e)}")
            return []