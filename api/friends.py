from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from core.db import get_db
# Friendships 모델만 사용합니다. (FriendRequest와 Friend 역할 모두 수행)
from core.models import User, Friendships 
from core.firebase_auth import verify_firebase_token

router = APIRouter(prefix="/friends", tags=["friends"])

# Pydantic 모델은 이전과 동일합니다.
class FriendRequestCreate(BaseModel):
     to_user: str 

class FriendRequestHandle(BaseModel):

     requester_uid: str # 요청을 보낸 사람의 Firebase UID
     action: str # "accept" 또는 "reject"

# =========================================================
# 유틸리티 함수: UID -> ID 변환
# =========================================================
def get_user_id_by_uid(db: Session, firebase_uid: str) -> int:
    """Firebase UID를 사용하여 User.id(PK)를 조회합니다."""
    user = db.query(User.id).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        # 이 함수는 검색 로직 내에서만 사용되므로 404를 발생시키지 않습니다.
        # User가 없으면 검색 결과에 포함되지 않을 것이기 때문입니다.
        return None 
    return user.id

# =========================================================
# 1) 닉네임으로 사용자 검색 API (관계 로직 추가)
# =========================================================
@router.get("/search", response_model=dict)
def search_users(
    query: str,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    if not query:
        return {"users": []}
    
    # 1. 현재 로그인한 사용자(나)의 DB ID를 가져옵니다.
    my_id = get_user_id_by_uid(db, uid)
    if my_id is None:
        raise HTTPException(status_code=404, detail="로그인된 사용자를 찾을 수 없습니다.")

    # 2. 닉네임에 검색어(query)가 포함된 사용자 조회 (본인 제외)
    users = db.query(User).filter(
        User.nickname.ilike(f"%{query.strip()}%"),
        User.firebase_uid != uid
    ).limit(50).all() 

    result_users = []
    for user in users:
        # 3. 나와 상대방(user)의 관계 확인
        relation_status = "none" # 기본 상태
        
        # 나와 상대방 사이에 Friendships 레코드가 있는지 확인
        # (내가 요청자 또는 수신자이면서 상태가 pending 또는 accepted인 경우)
        friendship = db.query(Friendships).filter(
            or_(
                # 내가 요청자이고 상대방이 수신자인 경우
                and_(Friendships.requester_id == my_id, Friendships.receiver_id == user.id),
                # 상대방이 요청자이고 내가 수신자인 경우
                and_(Friendships.requester_id == user.id, Friendships.receiver_id == my_id)
            )
        ).first()

        if friendship:
            if friendship.status == "accepted":
                # 이미 친구 관계입니다.
                relation_status = "friend"
            elif friendship.status == "pending":
                # 요청이 진행 중입니다. 누가 요청했는지 확인합니다.
                if friendship.requester_id == my_id:
                    # 내가 보낸 요청
                    relation_status = "sent_request" # 요청 완료
                else:
                    # 상대방이 보낸 요청 (받은 요청)
                    relation_status = "received_request" # 수락/거절 버튼 표시 필요

        # 4. 필요한 정보와 함께 관계 상태를 추가하여 응답
        result_users.append({
            "firebase_uid": user.firebase_uid,
            "nickname": user.nickname,
            "profile_image": user.profile_image,
            "relation_status": relation_status # 추가된 핵심 필드
        })

    return {"users": result_users}

# =========================================================
# 2) 친구 요청 생성 API (Friendships 모델에 맞게 수정)
# =========================================================
@router.post("/request")
def create_friend_request(
    data: FriendRequestCreate,
    uid: str = Depends(verify_firebase_token), # 요청을 보내는 사람 (from_user_uid)
    db: Session = Depends(get_db)
):
    from_uid = uid
    to_uid = data.to_user

    if from_uid == to_uid:
        raise HTTPException(status_code=400, detail="자기 자신에게는 친구 요청을 보낼 수 없습니다.")
    
    # UID를 DB ID로 변환
    from_id = get_user_id_by_uid(db, from_uid)
    to_id = get_user_id_by_uid(db, to_uid)

    # 이미 친구 요청이 있는지 확인 (양방향, 상태 상관없이)
    existing_request = db.query(Friendships).filter(
        or_(
            and_(Friendships.requester_id == from_id, Friendships.receiver_id == to_id), # 내가 보낸 요청
            and_(Friendships.requester_id == to_id, Friendships.receiver_id == from_id)  # 상대방이 나에게 보낸 요청
        )
    ).first()

    if existing_request:
        if existing_request.status == "pending":
            raise HTTPException(status_code=409, detail="이미 친구 요청이 전송되었거나, 상대방에게 받은 요청이 있습니다.")
        if existing_request.status == "accepted":
            raise HTTPException(status_code=409, detail="이미 친구입니다.")
        # rejected 상태라면 재요청이 가능하도록 로직을 추가할 수 있으나, 일단은 충돌 처리

    # 새로운 친구 요청 생성 (status='pending'은 기본값)
    new_request = Friendships(
        requester_id=from_id,
        receiver_id=to_id,
        status="pending"
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    return {"message": "친구 요청이 성공적으로 전송되었습니다."} # ID가 Primary Key에 없으므로 request_id 반환을 생략


# =========================================================
# 3) 받은 친구 요청 목록 조회 API (Friendships 모델에 맞게 수정)
# =========================================================
@router.get("/requests", response_model=dict)
def get_friend_requests(
    uid: str = Depends(verify_firebase_token), # 현재 로그인 사용자 (receiver_uid)
    db: Session = Depends(get_db)
):
    # UID를 DB ID로 변환
    receiver_id = get_user_id_by_uid(db, uid)

    # 'receiver_id'가 현재 로그인된 사용자(ID)인 'pending' 상태 요청 조회
    pending_requests = db.query(Friendships).filter(
        Friendships.receiver_id == receiver_id,
        Friendships.status == "pending"
    ).all()

    results = []
    for req in pending_requests:
        # 요청을 보낸 사용자 정보(닉네임, 프로필)를 가져옵니다.
        # User.id와 Friendships.requester_id를 이용해 조인하여 닉네임을 가져옵니다.
        from_user = db.query(User).filter(User.id == req.requester_id).first()
        if from_user:
            results.append({
                # request_id가 없으므로 요청 보낸 사람의 UID를 키로 사용합니다.
                "from_user_uid": from_user.firebase_uid, 
                "from_user_nickname": from_user.nickname,
                "from_user_profile_image": from_user.profile_image,
            })
    
    return {"requests": results}


# =========================================================
# 4) 친구 요청 처리 API (Friendships 모델에 맞게 수정)
# =========================================================
@router.post("/handle")
def handle_friend_request(
    data: FriendRequestHandle, # 이제 requester_uid를 받습니다.
    uid: str = Depends(verify_firebase_token), # 요청을 처리하는 사람 (receiver_uid)
    db: Session = Depends(get_db)
):
    receiver_id = get_user_id_by_uid(db, uid)
    requester_id = get_user_id_by_uid(db, data.requester_uid)

    # 1. 요청 찾기: 'requester'가 data.requester_uid이고, 'receiver'가 현재 나(uid)인 'pending' 요청
    request = db.query(Friendships).filter(
        Friendships.requester_id == requester_id,
        Friendships.receiver_id == receiver_id, 
        Friendships.status == "pending"
    ).first()

    if not request:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없거나 이미 처리되었습니다.")

    # 2. 처리 (수락 또는 거절)
    if data.action == "accept":
        # 상태를 'accepted'로 변경
        request.status = "accepted"
        
        # Friendships 모델이 친구 관계 자체를 저장하므로, 별도의 Friend 테이블에 추가할 필요가 없습니다.
        # 다만, 양방향 조회 편의를 위해 Friendships 테이블에 반대 방향 관계를 추가할 수도 있으나
        # 현재 Friendships 모델의 primary_key 정의(requester_id, receiver_id)를 보면 이는 불가능합니다.
        # 따라서 현재는 이 레코드 하나가 두 사람의 친구 관계를 대표합니다.
        
        db.commit()
        return {"message": "친구가 되었습니다."}

    elif data.action == "reject":
        request.status = "rejected"
        db.commit()
        return {"message": "요청을 거절했습니다."}

    else:
        raise HTTPException(status_code=400, detail="유효하지 않은 action입니다.")