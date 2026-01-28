"""
쓰레기통/탐지/통계 DB 모델 정의.
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Date,
    Integer,
    Numeric,
    String,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class TrashCan(Base):
    """쓰레기통 기본 정보 및 현재 상태."""

    __tablename__ = "TrashCan"

    trashcan_id = Column(BigInteger, primary_key=True, autoincrement=True)
    trashcan_name = Column(String(255))
    trashcan_capacity = Column(Integer)
    trashcan_city = Column(String(100))
    address_detail = Column(String(255))
    trashcan_latitude = Column(Numeric(10, 8))
    trashcan_longitude = Column(Numeric(11, 8))
    is_online = Column(Boolean, default=False)
    last_connected_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)

    detections = relationship("Detection", back_populates="trashcan")


class WasteType(Base):
    """쓰레기 종류 마스터."""

    __tablename__ = "WasteType"

    waste_type_id = Column(BigInteger, primary_key=True, autoincrement=True)
    type_name = Column(String(50), unique=True, nullable=False, index=True)

    detection_details = relationship("DetectionDetail", back_populates="waste_type")
    daily_stats = relationship("DailyStats", back_populates="waste_type")


class Detection(Base):
    """탐지 이벤트(이미지 단위)."""

    __tablename__ = "Detection"

    detection_id = Column(BigInteger, primary_key=True, autoincrement=True)
    trashcan_id = Column(BigInteger, ForeignKey("TrashCan.trashcan_id"), nullable=False, index=True)
    image_name = Column(String(255))
    image_path = Column(String(512))
    detected_at = Column(DateTime, default=func.now(), nullable=False)
    object_count = Column(Integer)

    trashcan = relationship("TrashCan", back_populates="detections")
    details = relationship("DetectionDetail", back_populates="detection")


class DetectionDetail(Base):
    """탐지 상세 결과(개별 객체)."""

    __tablename__ = "Detection_detail"

    detail_id = Column(BigInteger, primary_key=True, autoincrement=True)
    detection_id = Column(BigInteger, ForeignKey("Detection.detection_id"), nullable=False, index=True)
    waste_type_id = Column(BigInteger, ForeignKey("WasteType.waste_type_id"), nullable=False, index=True)
    confidence = Column(Numeric(5, 4))
    bbox_info = Column(JSON)

    detection = relationship("Detection", back_populates="details")
    waste_type = relationship("WasteType", back_populates="detection_details")


class DailyStats(Base):
    """일별 탐지 통계."""

    __tablename__ = "DailyStats"

    stats_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stats_date = Column(Date, nullable=False, index=True)
    trashcan_city = Column(String(100))
    waste_type_id = Column(BigInteger, ForeignKey("WasteType.waste_type_id"), nullable=False, index=True)
    detection_count = Column(BigInteger)

    waste_type = relationship("WasteType", back_populates="daily_stats")
