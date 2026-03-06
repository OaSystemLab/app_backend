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
        'dev_status_oxy_state', 'dev_status_vent_state', 'dev_status_led_state',
        'dev_status_rout_num',
        'reservation',
        'dev_status_lcd_state','dev_sleep_enable', 'dev_sleep_moodlamp' ,'dev_sleep_diallamp', 'dev_sleep_bed_time', 'dev_sleep_wake_up_time'
    ]
    # 조회를 허용할 테이블 목록
    ALLOWED_TABLES = {'st_dev_sensing', 'st_senser_hourly'}

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
                f"LIMIT 1000000"
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

    def _execute_sensor_query(self, table_name, sitecode, select_clause, start_time, end_time):
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
            # 컬럼명/테이블명은 위에서 검증된 safe 변수 사용
            # 값(sitecode, 시간)은 %s 파라미터 바인딩 사용
            # query = (
            #     f"SELECT ts{safe_select_str} FROM {table_name} "
            #     f"WHERE sitecode = %s "
            #     f"AND ts >= %s AND ts <= %s "
            #     f"ORDER BY ts DESC "
            #     f"LIMIT 1000000"
            # )

            # params = (sitecode, start_time, end_time)
            # cursor.execute(query, params)

            # return cursor.fetchall()

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

    # 공개 메서드들
    def get_history_data(self, sitecode, select_clause, start_time, end_time):
        return self._execute_sensor_query(
            "st_dev_sensing", sitecode, select_clause, start_time, end_time
        )

    def get_hourly_data(self, sitecode, select_clause, start_time, end_time):
        return self._execute_sensor_query(
            "st_senser_hourly", sitecode, select_clause, start_time, end_time
        )
# 전역 인스턴스 생성 (다른 앱에서 import 하여 사용)
td_service = TDengineService()