from sqlalchemy import Column,Integer,String,Text
from app.database.base import Base

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    campaign_name = Column(String(255))
    objective = Column(Text)
    ai_prompt = Column(Text)