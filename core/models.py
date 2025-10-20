from sqlalchemy import Column, Integer, String, Date, Time, DateTime, Boolean, Float, TIMESTAMP, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy import func
from core.db import Base

class User(Base):
    __tablename__ = "Users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    firebase_uid = Column(String(128), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    nickname = Column(String(50))
    gender = Column(String(10), nullable=False)
    birth_date = Column(Date, nullable=False)
    birth_time = Column(Time, nullable=True)
    birth_calendar = Column(String(20), nullable=False, default="solar")
    profile_image = Column(String(255), nullable=True)
    oheng_wood = Column(Float, nullable=True)
    oheng_fire = Column(Float, nullable=True)
    oheng_earth = Column(Float, nullable=True)
    oheng_metal = Column(Float, nullable=True)
    oheng_water = Column(Float, nullable=True)
    day_sky = Column(String(10), nullable=True)

class Manse(Base):
    __tablename__ = "manses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    solarDate = Column(Date, nullable=False)
    lunarDate = Column(Date, nullable=False)
    season = Column(String(10))
    seasonStartTime = Column(DateTime, default=None)
    leapMonth = Column(Boolean)
    yearSky = Column(String(10))
    yearGround = Column(String(10))
    monthSky = Column(String(10))
    monthGround = Column(String(10))
    daySky = Column(String(10))
    dayGround = Column(String(10))
    
class ChatRoom(Base):
    __tablename__ = 'Chat_rooms'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(30), nullable=True)
    is_group = Column(Boolean, nullable=False, default=False)
    last_message_id = Column(Integer, nullable=True) 
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now())

    members = relationship("ChatroomMember", back_populates="chatroom", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="chatroom", cascade="all, delete-orphan")

class ChatroomMember(Base):
    __tablename__ = 'Chatroom_members'

    user_id = Column(Integer, ForeignKey('Users.id'), primary_key=True) 
    chatroom_id = Column(Integer, ForeignKey('Chat_rooms.id'), primary_key=True)
    
    role = Column(String(20), nullable=False, default='member')
    joined_at = Column(TIMESTAMP, nullable=False, default=func.now())

    chatroom = relationship("ChatRoom", back_populates="members")

class ChatMessage(Base):
    __tablename__ = 'Chat_messages'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('Users.id'), nullable=False) 
    chatroom_id = Column(Integer, ForeignKey('Chat_rooms.id'), nullable=False)
    
    content = Column(Text, nullable=False)
    message_type = Column(Enum('text', 'image'), nullable=False, default='text')
    image_url = Column(String(255), nullable=True)
    send_at = Column(TIMESTAMP, nullable=False, default=func.now())

    chatroom = relationship("ChatRoom", back_populates="messages")