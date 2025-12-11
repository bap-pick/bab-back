from typing import List, Dict, Any
from core.redis_client import get_redis_client
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.models import Restaurant, Reviews

class RestaurantCacheService:
    def __init__(self):
        self.redis_client = get_redis_client()
        # 식당 요약 정보를 저장할 키 패턴
        self.summary_key_prefix = "restaurant:summary:"

    def get_summary_key(self, restaurant_id: int) -> str:
        return f"{self.summary_key_prefix}{restaurant_id}"

    # 1. DB에서 요약 정보를 가져와 Redis에 저장하는 함수
    def cache_restaurant_summary(self, restaurant_id: int, db: Session):
        
        # DB에서 필요한 정보와 평점/리뷰 수를 JOIN하여 한 번에 조회
        result = db.query(
            Restaurant,
            Reviews.rating,
            (func.coalesce(Reviews.visitor_reviews, 0) + func.coalesce(Reviews.blog_reviews, 0)).label('review_count')
        ).outerjoin(
            Reviews, Restaurant.id == Reviews.restaurant_id
        ).filter(
            Restaurant.id == restaurant_id
        ).first()

        if not result:
            return False

        restaurant, rating, review_count = result
        
        # Redis Hash에 저장할 데이터 구성
        data = {
            "name": restaurant.name or "",
            "category": restaurant.category or "",
            "address": restaurant.address or "",
            "image": restaurant.image or "",
            "rating": float(rating) if rating else 0.0,
            "review_count": int(review_count) if review_count else 0,
            "latitude": restaurant.latitude or 0.0,
            "longitude": restaurant.longitude or 0.0,
        }

        # Redis Hash에 저장 (HSET)
        key = self.get_summary_key(restaurant_id)
        # Redis-py는 float을 직접 저장할 수 없으므로 문자열로 변환
        data_to_store = {k: str(v) for k, v in data.items()}
        self.redis_client.hset(key, mapping=data_to_store)
        
        return True

    # 2. Redis에서 ID 목록의 요약 정보를 한 번에 가져오는 함수
    def get_summaries_by_ids(self, restaurant_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        pipeline = self.redis_client.pipeline()
        
        for r_id in restaurant_ids:
            pipeline.hgetall(self.get_summary_key(r_id))
        
        results = pipeline.execute()
        
        summaries = {}
        for r_id, raw_data in zip(restaurant_ids, results):
            if raw_data:
                name_val = raw_data.get('name', 'N/A')
                category_val = raw_data.get('category', 'N/A')
                address_val = raw_data.get('address', 'N/A')
                image_val = raw_data.get('image', '')
                rating_str = raw_data.get('rating', '0.0')
                review_count_str = raw_data.get('review_count', '0')
                latitude_str = raw_data.get('latitude', '0.0')
                longitude_str = raw_data.get('longitude', '0.0')
                
                summaries[r_id] = {
                    "id": r_id,
                    "name": name_val,
                    "category": category_val,
                    "address": address_val,
                    "image": image_val,
                    "rating": float(rating_str),
                    "review_count": int(review_count_str),
                    "latitude": float(latitude_str),
                    "longitude": float(longitude_str),
                }
        return summaries
      
    # 3. 모든 식당 정보를 DB에서 가져와 Redis에 일괄 저장하는 함수 (Bulk Load)
    def cache_all_restaurant_summaries(self, db: Session):
        
        results = db.query(
            Restaurant.id,
            Restaurant.name,
            Restaurant.category,
            Restaurant.address,
            Restaurant.image,
            Reviews.rating.label('rating'),
            (func.coalesce(Reviews.visitor_reviews, 0) + func.coalesce(Reviews.blog_reviews, 0)).label('review_count'),
            Restaurant.latitude,
            Restaurant.longitude
        ).outerjoin(
            Reviews, Restaurant.id == Reviews.restaurant_id
        ).all()
        
        if not results:
            print("Redis에 로드할 식당 데이터 없음")
            return

        print(f"DB에서 총 {len(results)}개 식당 요약 정보 조회 완료")

        # 2. Redis Pipeline을 사용하여 일괄 처리
        pipeline = self.redis_client.pipeline()
        total_cached = 0
        
        for r_id, name, category, address, image, rating, review_count, latitude, longitude in results:
            # Redis Hash에 저장할 데이터 구성
            data = {
                "name": name or "",
                "category": category or "", 
                "address": address or "", 
                "image": image or "",
                "rating": float(rating) if rating is not None else 0.0,
                "review_count": int(review_count) if review_count is not None else 0,
                "latitude": latitude or 0.0,
                "longitude": longitude or 0.0,
            }
            
            data_to_store = {k: str(v) for k, v in data.items()}
            
            key = self.get_summary_key(r_id)
            
            # Pipeline에 HSET 명령을 추가
            pipeline.hset(key, mapping=data_to_store)
            total_cached += 1
            
        # 3. 모든 명령을 한 번에 실행
        print(f"Pipeline 실행 중 ({total_cached}개 식당 캐싱)")
        pipeline.execute()
        
        print(f"Redis에 총 {total_cached}개 식당 요약 정보 로드 완료!")