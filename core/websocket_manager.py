import logging
from typing import List, Dict
from fastapi import WebSocket

# 로깅 설정
logger = logging.getLogger(__name__)

# ConnectionManager 클래스: 모든 활성 WebSocket 연결을 room_id별로 저장, 관리
class ConnectionManager:
    # {room_id: [{uid: str, websocket: WebSocket}, ...]}
    def __init__(self):
        self.active_connections: Dict[int, List[Dict]] = {}

    # 새로운 WebSocket 연결을 수락, 등록
    async def connect(self, room_id: int, uid: str, websocket: WebSocket):
        await websocket.accept()
        
        connection_info = {"uid": uid, "websocket": websocket}
        
        # 해당 room_id가 없으면 새로 생성
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        
        # 연결 추가
        self.active_connections[room_id].append(connection_info)
        logger.info(f"WebSocket connected: Room {room_id}, User {uid}. Total connections: {len(self.active_connections[room_id])}")

    # WebSocket 연결 해제, 관리자에서 제거
    def disconnect(self, room_id: int, websocket: WebSocket):
        if room_id in self.active_connections:
            # 해당 WebSocket 객체를 찾아 리스트에서 제거
            self.active_connections[room_id] = [
                conn for conn in self.active_connections[room_id] 
                if conn["websocket"] is not websocket
            ]
            
            # 리스트가 비면 방 정보 제거 (메모리 관리)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        
        logger.info(f"WebSocket disconnected: Room {room_id}. Remaining connections in room: {len(self.active_connections.get(room_id, []))}")

    # 특정 방에 연결된 모든 클라이언트에게 메시지를 브로드캐스트
    async def broadcast(self, room_id: int, message: str):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                try:
                    await connection["websocket"].send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting message to room {room_id}, user {connection['uid']}: {e}")

# ConnectionManager 인스턴스를 싱글톤으로 생성
manager = ConnectionManager()

# 의존성 주입을 위한 함수: FastAPI Dependencies를 통해 ConnectionManager 인스턴스 제공
def get_connection_manager():
    return manager