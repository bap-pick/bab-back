# DB 테이블과 매핑되는 SQLAlchemy 모델을 정의
from sqlalchemy import Column, Integer, String, Date, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime
from core.db import Base

Base = declarative_base()

class User(Base):
    __tablename__ = "Users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    firebase_uid = Column(String(128), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    nickname = Column(String(50))
    gender = Column(String(1), nullable=False)
    birth_date = Column(Date, nullable=False)
    birth_time = Column(Time, nullable=True)
    birth_calendar = Column(String(20), nullable=False, default="solar")
    profile_image = Column(String(255), nullable=True)