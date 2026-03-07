from sqlalchemy import Column, Integer, Text
from app.db.base import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    terms_and_conditions = Column(Text, default="Enter your terms and conditions here.")
    contest_rules = Column(Text, default="Enter your contest rules here.")