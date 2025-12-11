import sys
from core.db import get_db
from services.restaurant_cache_service import RestaurantCacheService
from services.restaurant_service import RestaurantLocationService

def main():
    db = next(get_db())
    try:
        # 식당 요약 정보 캐싱 (Redis Hash)
        print("[1/2] 식당 요약 정보(Hash) 캐싱 시작")
        summary_cache_service = RestaurantCacheService()
        summary_cache_service.cache_all_restaurant_summaries(db)
        print("[1/2] 식당 요약 정보 캐싱 완료.")

        # 식당 위치 정보 캐싱 (Redis GeoSet)
        print("[2/2] 식당 위치 정보(GeoSet) 캐싱 시작...")
        location_service = RestaurantLocationService()
        location_service.load_from_db(db) 
        print("[2/2] 식당 위치 정보 캐싱 완료.")
        
    except Exception as e:
        print(f"캐싱 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        # 오류 발생 시 프로세스를 중단
        sys.exit(1)
        
    finally:
        # 세션 닫기
        db.close()
        print("모든 초기 캐싱 작업 완료. DB 세션 종료.")

if __name__ == "__main__":
    main()