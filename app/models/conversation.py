from sqlalchemy import Column,Integer,String,Text,DateTime
from datetime import datetime
from app.database.base import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer)
    call_sid = Column(String(255), index=True, nullable=True)
    event_id = Column(String(255), unique=True, nullable=True)
    speaker = Column(String(20), nullable=False)
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
