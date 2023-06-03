import sqlalchemy
from sqlalchemy import Column, ForeignKey, String, Integer
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import settings

Base = declarative_base()
metadata = sqlalchemy.MetaData()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    token = Column(String)
    audio_record = relationship("AudioRecord", back_populates="user")


class AudioRecord(Base):
    __tablename__ = 'audio_records'
    id = Column(String, primary_key=True)
    file_name = Column(String)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship("User", back_populates="audio_record")


engine = sqlalchemy.create_engine(settings.db_url)
metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
