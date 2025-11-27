from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from core.db import get_db
from core.models import User, Friendships 
from core.firebase_auth import verify_firebase_token

router = APIRouter(prefix="/friends", tags=["friends"])


class FriendRequestCreate(BaseModel):
    to_user: str 

class FriendRequestHandle(BaseModel):
    requester_uid: str
    action: str

# =========================================================
# 유틸리티 함수: UID -> ID 변환
# =========================================================
def get_user_id_by_uid(db: Session, firebase_uid: str) -> int:
    """Firebase UID를 사용하여 User.id(PK)를 조회합니다."""
    user = db.query(User.id).filter(User.firebase_uid == firebase_uid).first()
    return user.id if user else None

# =========================================================
# 닉네임으로 사용자 검색 API
# =========================================================
@router.get("/search", response_model=dict)
def search_users(
    query: str,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    if not query:
        return {"users": []}
    
    my_id = get_user_id_by_uid(db, uid)
    if my_id is None:
        raise HTTPException(status_code=404, detail="로그인된 사용자를 찾을 수 없습니다.")

    users = db.query(User).filter(
        User.nickname.ilike(f"%{query.strip()}%"),
        User.firebase_uid != uid
    ).limit(50).all() 

    result_users = []
    for user in users:
        relation_status = "none"
        
        friendship = db.query(Friendships).filter(
            or_(
                and_(Friendships.requester_id == my_id, Friendships.receiver_id == user.id),
                and_(Friendships.requester_id == user.id, Friendships.receiver_id == my_id)
            )
        ).first()

        if friendship:
            if friendship.status == "accepted":
                relation_status = "friend"
            elif friendship.status == "pending":
                if friendship.requester_id == my_id:
                    relation_status = "sent_request"
                else:
                    relation_status = "received_request"

        result_users.append({
            "firebase_uid": user.firebase_uid,
            "nickname": user.nickname,
            "profile_image": user.profile_image,
            "relation_status": relation_status
        })

    return {"users": result_users}

# =========================================================
# 친구 요청 생성 API
# =========================================================
@router.post("/request")
def create_friend_request(
    data: FriendRequestCreate,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    from_uid = uid
    to_uid = data.to_user

    if from_uid == to_uid:
        raise HTTPException(status_code=400, detail="자기 자신에게는 친구 요청을 보낼 수 없습니다.")
    
    from_id = get_user_id_by_uid(db, from_uid)
    to_id = get_user_id_by_uid(db, to_uid)

    if from_id is None or to_id is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    
    existing_request = db.query(Friendships).filter(
        or_(
            and_(Friendships.requester_id == from_id, Friendships.receiver_id == to_id),
            and_(Friendships.requester_id == to_id, Friendships.receiver_id == from_id)
        )
    ).first()

    if existing_request:
        if existing_request.status == "pending":
            raise HTTPException(status_code=409, detail="이미 친구 요청이 전송되었거나, 상대방에게 받은 요청이 있습니다.")
        if existing_request.status == "accepted":
            raise HTTPException(status_code=409, detail="이미 친구입니다.")

    new_request = Friendships(
        requester_id=from_id,
        receiver_id=to_id,
        status="pending"
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    return {"message": "친구 요청이 성공적으로 전송되었습니다."}

# =========================================================
# 받은 친구 요청 목록 조회 API
# =========================================================
@router.get("/requests", response_model=dict)
def get_friend_requests(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    receiver_id = get_user_id_by_uid(db, uid)

    if receiver_id is None:
        raise HTTPException(status_code=404, detail="로그인된 사용자를 찾을 수 없습니다.")

    pending_requests = db.query(Friendships).filter(
        Friendships.receiver_id == receiver_id,
        Friendships.status == "pending"
    ).all()

    results = []
    for req in pending_requests:
        from_user = db.query(User).filter(User.id == req.requester_id).first()
        if from_user:
            results.append({
                "from_user_uid": from_user.firebase_uid, 
                "from_user_nickname": from_user.nickname,
                "from_user_profile_image": from_user.profile_image,
            })
    
    return {"requests": results}


# =========================================================
# 친구 요청 처리 API
# =========================================================
@router.post("/handle")
def handle_friend_request(
    data: FriendRequestHandle,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    receiver_id = get_user_id_by_uid(db, uid)
    requester_id = get_user_id_by_uid(db, data.requester_uid)

    if receiver_id is None or requester_id is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    request = db.query(Friendships).filter(
        Friendships.requester_id == requester_id,
        Friendships.receiver_id == receiver_id, 
        Friendships.status == "pending"
    ).first()

    if not request:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없거나 이미 처리되었습니다.")

    if data.action == "accept":
        request.status = "accepted"
        db.commit()
        return {"message": "친구가 되었습니다."}

    elif data.action == "reject":
        request.status = "rejected"
        db.commit()
        return {"message": "요청을 거절했습니다."}

    else:
        raise HTTPException(status_code=400, detail="유효하지 않은 action입니다.")


# =========================================================
# 친구 목록 조회 API (GET /friends/list)
# =========================================================
@router.get("/list", response_model=dict)
def get_friends_list(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    current_user_id = get_user_id_by_uid(db, uid)

    if current_user_id is None:
        raise HTTPException(status_code=404, detail="로그인된 사용자를 찾을 수 없습니다.")

    accepted_friendships = db.query(Friendships).filter(
        and_(
            or_(
                Friendships.requester_id == current_user_id,
                Friendships.receiver_id == current_user_id
            ),
            Friendships.status == "accepted"
        )
    ).all()

    friend_ids = []
    for friendship in accepted_friendships:
        if friendship.requester_id == current_user_id:
            friend_ids.append(friendship.receiver_id)
        else:
            friend_ids.append(friendship.requester_id)
            
    friends_info = db.query(User).filter(User.id.in_(friend_ids)).all()

    results = []
    for friend in friends_info:
        results.append({
            "firebase_uid": friend.firebase_uid,
            "nickname": friend.nickname,
            "profile_image": friend.profile_image,
        })
        
    return {"friends": results}

# =========================================================
# 친구 삭제 API (DELETE /friends/{target_user_uid}) 
# =========================================================
@router.delete("/{target_user_uid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_friend(
    target_user_uid: str,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    my_uid = uid
    if my_uid == target_user_uid:
        raise HTTPException(status_code=400, detail="자기 자신을 친구 목록에서 삭제할 수 없습니다.")

    my_id = get_user_id_by_uid(db, my_uid)
    target_id = get_user_id_by_uid(db, target_user_uid)
    
    if my_id is None or target_id is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 친구 관계(accepted 상태) 찾기
    friendship = db.query(Friendships).filter(
        and_(
            Friendships.status == "accepted",
            or_(
                # case 1: 내가 요청자, 상대방이 수신자
                and_(Friendships.requester_id == my_id, Friendships.receiver_id == target_id),
                # case 2: 상대방이 요청자, 내가 수신자
                and_(Friendships.requester_id == target_id, Friendships.receiver_id == my_id)
            )
        )
    ).first()

    if not friendship:
        # 프론트엔드에서 404를 처리합니다.
        raise HTTPException(status_code=404, detail="친구 관계를 찾을 수 없습니다.")

    # 친구 관계 삭제
    db.delete(friendship)
    db.commit()

    return
