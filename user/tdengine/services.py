import taos
from datetime import datetime
from django.conf import settings

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
        return taos.connect(
            host=cfg['HOST'], user=cfg['USER'],
            password=cfg['PASSWORD'], database=cfg['DB']
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

# 전역 인스턴스 생성 (다른 앱에서 import 하여 사용)
td_service = TDengineService()


class DashboardService:
    @staticmethod
    def __client():
        cfg = settings.TDENGINE_CONFIG
        return taos.connect(
            host=cfg['HOST'], user=cfg['USER'],
            password=cfg['PASSWORD'], database=cfg['DB']
        )
    def _execute_query(self, v_data, tname):

        conn = self.__client()
        cursor = conn.cursor()
        try:
            # serivalzer 에서
            # select * from dev.userapp_dashboard_analysis where sitecode = '11650001010102111' order by ts desc limit 1
            query = (
                f"SELECT * FROM {tname} "
                f"WHERE home_sitecode = '{v_data['sitecode'][:-1]}' "
                f"ORDER BY ts DESC " # 최신순 정렬
                f"LIMIT 1"
            )

            cursor.execute(query)

            # TDengine에서 컬럼명 가져오기 (결과를 딕셔너리로 만들기 위함)
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone() # LIMIT 1이므로 fetchone이 효율적입니다.

            if row:
                # [(값1, 값2)] 형태를 {'컬럼1': 값1, '컬럼2': 값2} 형태로 변환
                return dict(zip(columns, row))
            return {} # 데이터가 없을 경우 빈 객체 반환

            #return cursor.fetchall()

        finally:
            cursor.close()
            conn.close()

    def _execute_query2(self, v_data, tname):

        conn = self.__client()
        cursor = conn.cursor()
        res = {"dev": {}, "site": {}}
        try:
            # --- [1] 첫 번째 쿼리: 최신 대시보드 데이터 (1행) ---
            query1 = (
                f"SELECT * FROM userapp_analysis_dev "
                f"WHERE sitecode = '{v_data['sitecode']}' "
                f"AND ts > NOW - 7d "  # 7일 이내 데이터가 없으면 즉시 종료되어 DB 부하 방지
                f"ORDER BY ts DESC LIMIT 1"
            )
            cursor.execute(query1)
            cols1 = [col[0] for col in cursor.description]
            row1 = cursor.fetchone()

            # 데이터가 없으면 즉시 빈 객체 반환
            if not row1:
                return res

            res['dev'] = dict(zip(cols1, row1))

            # --- [2] 두 번째 쿼리: 단지(Site) 데이터 ---
            # 슬라이싱(Site Key 추출)
            site_key = v_data['sitecode'][:-9]

            query2 = (
                f"SELECT * FROM userapp_analysis_site "
                f"WHERE site = '{site_key}' "
                f"AND ts > NOW - 7d "  # 7일 이내 데이터가 없으면 즉시 종료되어 DB 부하 방지
                f"ORDER BY ts DESC LIMIT 1"
            )
            cursor.execute(query2)
            cols2 = [col[0] for col in cursor.description]
            row2 = cursor.fetchone() # 단지 데이터도 최신 1개만 가져오므로 fetchone

            # 'site' 키에 단지 정보 저장 (데이터가 없을 경우 빈 딕셔너리)
            if row2:
                res['site'] = dict(zip(cols2, row2))
            else:
                res['site'] = {}

            # 최종적으로 { "dev": {...}, "site": {...} } 형태가 리턴됩니다.
            return res

        finally:
            cursor.close()
            conn.close()

    def _execute_query3(self, v_data, tname):

        conn = self.__client()
        cursor = conn.cursor()
        try:
            # serivalzer 에서
            # select * from dev.userapp_dashboard_analysis where sitecode = '11650001010102111' order by ts desc limit 1
            query = (
                f"SELECT * FROM {tname} "
                f"WHERE sitecode = '{v_data['sitecode']}' "
                f"ORDER BY ts DESC " # 최신순 정렬
                f"LIMIT 1"
            )

            cursor.execute(query)

            # TDengine에서 컬럼명 가져오기 (결과를 딕셔너리로 만들기 위함)
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone() # LIMIT 1이므로 fetchone이 효율적입니다.

            if row:
                # [(값1, 값2)] 형태를 {'컬럼1': 값1, '컬럼2': 값2} 형태로 변환
                return dict(zip(columns, row))
            return {} # 데이터가 없을 경우 빈 객체 반환

            #return cursor.fetchall()

        finally:
            cursor.close()
            conn.close()
    # 공개 메서드들
    def get_dashboard(self, v_data):
        match v_data['data_type']:
            case "a1":
                return self._execute_query(v_data, "userapp_dashboard_analysis")
            case "a2":
                return self._execute_query2(v_data, "userapp_analysis")
            case "a3":
                return self._execute_query3(v_data, "userapp_dashboard")

db_service = DashboardService()