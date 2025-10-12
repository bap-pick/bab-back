# DB 테이블과 매핑되는 SQLAlchemy 모델을 정의
from sqlalchemy import Column, Integer, String, Date, Time, DateTime, Boolean, Float
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