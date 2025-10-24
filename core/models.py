from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Date, Time, DateTime, Boolean, Float, Text, ForeignKey
from core.db import Base
from datetime import datetime

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

class ChatRoom(Base):
    __tablename__ = "Chat_rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(30), nullable=True)     
    is_group = Column(Boolean, nullable=False, default=False)    
    last_message_id = Column(Integer, nullable=True) 
    
class ChatMessage(Base):
    __tablename__ = "Chat_messages"
    id = Column(Integer, primary_key=True) #메세지 고유 id
    room_id = Column(Integer)   # 채팅방 id..chat_rooms.id
    sender_id = Column(String) # 메세지 보낸사람
    role = Column(String) # 유저인지 ai 인지
    content = Column(Text) #내용
    timestamp = Column(DateTime, default=datetime.utcnow) #보낸시간

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

class Restaurant(Base):
    __tablename__ = "Restaurants"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    address = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=True)
    
    # 식당의 상위 오행 3개를 저장합니다. (예: 木, 火, 土)
    top_ohaeng_1 = Column(String(10), nullable=True)
    top_ohaeng_2 = Column(String(10), nullable=True)
    top_ohaeng_3 = Column(String(10), nullable=True)
    
    # Menu 모델과 연결: Restaurant 객체에서 rest.menus로 메뉴 리스트를 가져오기 위함
    menus = relationship("Menu", back_populates="restaurant")

    def __repr__(self):
        return f"<Restaurant(id={self.id}, name='{self.name}', category='{self.category}')>"

class Menu(Base):
    __tablename__ = "Menus"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    menu_name = Column(String(100), nullable=True)
    restaurant_id = Column(Integer, ForeignKey('Restaurants.id'), nullable=False)
    
    # Restaurant 모델과 연결: Menu 객체에서 menu.restaurant로 해당 식당 객체를 가져오기 위함
    restaurant = relationship("Restaurant", back_populates="menus")
    
    def __repr__(self):
        return f"<Menu(id={self.id}, menu_name='{self.menu_name}', restaurant_id={self.restaurant_id})>"