from typing import Optional, Dict
from core.redis_client import get_redis_client
import logging
from sqlalchemy.orm import Session
from core.models import Restaurant   

logger = logging.getLogger(__name__)

class RestaurantLocationService:    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.geo_key = "restaurants:geo"
    
    # Redis에서 1km 이내 식당 ID와 거리 조회
    def get_nearby_ids_with_distance(
        self, 
        longitude: float, 
        latitude: float, 
        radius_km: float = 1.0,
        limit: Optional[int] = None
    ) -> Dict[int, float]:
        try:
            results = self.redis_client.georadius(
                self.geo_key,
                longitude,
                latitude,
                radius_km,
                unit="km",
                withdist=True,
                sort="ASC",
                count=limit
            )
            
            return {int(r_id): float(dist) for r_id, dist in results}
            
        except Exception as e:
            logger.error(f"Redis 조회 실패: {e}")
            return {}
    
    # 식당 위치 정보 캐싱 (Redis GeoSet)
    def load_from_db(self, db: Session):
        GEO_KEY = "restaurants:geo"
        MAX_VALID_LATITUDE = 85.05112878 
        BATCH_SIZE = 1
        
        try:
            redis_client = get_redis_client()
            
            # 1. 이미 데이터가 Redis에 로드되었는지 확인
            if redis_client.exists(GEO_KEY):
                print("Redis GeoSet에 식당 데이터가 이미 존재합니다. DB 로드를 건너뜁니다.")
                return

            print("DB에서 식당 위치 데이터를 Redis에 로드하는 중...")

            # 2. DB에서 Restaurant 모델의 ID, 위도, 경도를 조회
            restaurants_data = db.query(
                Restaurant.id, 
                Restaurant.latitude, 
                Restaurant.longitude
            ).all()

            total_db_records = len(restaurants_data) 
            print(f"DB에서 총 {total_db_records}개의 식당 레코드를 조회했습니다.")
            
            # 3. Redis Pipeline 초기화
            pipeline = redis_client.pipeline()
            
            # 4. 데이터를 수집할 딕셔너리
            geo_data_mapping = {}
            count = 0
            skipped_count = 0
            
            for rest_id, lat, lon in restaurants_data:
                if lat is not None and lon is not None:
                    
                    try:
                        float_lat = float(lat)
                        float_lon = float(lon)
                    except (ValueError, TypeError) as e:
                        skipped_count += 1
                        continue
                    
                    if abs(float_lat) > MAX_VALID_LATITUDE or abs(float_lon) > 180.0:
                        skipped_count += 1
                        continue
                    
                    geo_data_mapping[str(rest_id)] = (float_lon, float_lat) 
                    count += 1
            
            # 5. 딕셔너리를 배치 단위로 나누어 파이프라인에 추가
            if count > 0:
                
                all_members = list(geo_data_mapping.keys())
                
                for i in range(0, len(all_members), BATCH_SIZE):
                    batch_keys = all_members[i:i + BATCH_SIZE]
                    
                    member_id = batch_keys[0]
                    lon, lat = geo_data_mapping[member_id]
                    
                    pipeline.execute_command('GEOADD', GEO_KEY, lon, lat, member_id)
                    
                
                # 6. Pipeline 실행
                pipeline.execute()
                
                print(f"Redis GeoSet에 총 {count}개 식당 정보 로드 완료.")
                
                total_skipped = total_db_records - count
                if total_skipped > 0:
                    print(f"총 {total_skipped}개의 레코드(위도/경도 정보 누락)가 로드에서 제외됨.")
                    if skipped_count > 0:
                        print(f"  (이 중 {skipped_count}개는 유효하지 않은 좌표({MAX_VALID_LATITUDE} 초과 등)로 인해 스킵)")
            
            else:
                print("Redis에 로드할 유효한 식당 데이터가 없습니다.")
            
        except Exception as e:
            print(f"ERROR: Redis GeoSet 초기 데이터 로드 중 오류 발생 - {e}")
            raise