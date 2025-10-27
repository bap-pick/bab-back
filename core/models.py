from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Date, Time, DateTime, Boolean, Float, Text, ForeignKey, DECIMAL
from core.db import Base
from datetime import datetime
from typing import List

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
    
    scraps = relationship("Scrap", back_populates="user")

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
    
    # 식당의 상위 오행 3개를 저장
    top_ohaeng_1 = Column(String(10), nullable=True)
    top_ohaeng_2 = Column(String(10), nullable=True)
    top_ohaeng_3 = Column(String(10), nullable=True)
    
    menus = relationship("Menu", back_populates="restaurant")
    hours = relationship("OpeningHour", back_populates="restaurant")
    facility_associations = relationship("RestaurantFacility", back_populates="restaurant")
    reviews = relationship("Reviews", back_populates="restaurant")
    scraps = relationship("Scrap", back_populates="restaurant")
    
    @property
    def facilities(self) -> List["Facility"]:
        return [assoc.facility for assoc in self.facility_associations]

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
    
class OpeningHour(Base):
    __tablename__ = "OpeningHours"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    day = Column(String(10), nullable=True)
    open_time = Column(Time, nullable=True)
    close_time = Column(Time, nullable=True)
    break_start = Column(Time, nullable=True)
    break_end = Column(Time, nullable=True)
    last_order = Column(Time, nullable=True)
    is_closed = Column(Boolean, default=False)
    restaurant_id = Column(Integer, ForeignKey('Restaurants.id'), nullable=False)
    
    restaurant = relationship("Restaurant", back_populates="hours")
    
    def __repr__(self):
        return f"<OpeningHour(id={self.id}, day='{self.day}', restaurant_id={self.restaurant_id})>"

class RestaurantFacility(Base):
    __tablename__ = "RestaurantFacilities"
    
    restaurant_id = Column(Integer, ForeignKey("Restaurants.id"), primary_key=True)
    facility_id = Column(Integer, ForeignKey("Facilities.id"), primary_key=True)

    restaurant = relationship("Restaurant", back_populates="facility_associations")
    facility = relationship("Facility", back_populates="restaurants")

    def __repr__(self):
        return f"<RestaurantFacility(r_id={self.restaurant_id}, f_id={self.facility_id})>"

class Facility(Base):
    __tablename__ = "Facilities"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(100), nullable=True, unique=True)
    
    restaurants = relationship("RestaurantFacility", back_populates="facility")

    def __repr__(self):
        return f"<Facility(id={self.id}, name='{self.name}')>"
    
class Reviews(Base):
    __tablename__ = "Reviews"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    rating = Column(DECIMAL(3, 1), nullable=True) 
    visitor_reviews = Column(Integer, nullable=True, default=0)
    blog_reviews = Column(Integer, nullable=True, default=0)
    
    restaurant_id = Column(Integer, ForeignKey('Restaurants.id'), nullable=False)
    
    restaurant = relationship("Restaurant", back_populates="reviews")
    
    def __repr__(self):
        return f"<Reviews(id={self.id}, rating={self.rating}, restaurant_id={self.restaurant_id})>"

class Scrap(Base):
    __tablename__ = "Scraps"

    user_id = Column(Integer, ForeignKey('Users.id'), primary_key=True, nullable=False)
    restaurant_id = Column(Integer, ForeignKey('Restaurants.id'), primary_key=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="scraps")
    restaurant = relationship("Restaurant", back_populates="scraps")

    def __repr__(self):
        return f"<Scrap(user_id={self.user_id}, restaurant_id={self.restaurant_id})>" 
    