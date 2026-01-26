"""
FastAPI 진입점.

- /detections: YOLO 결과 저장
- /health: 헬스체크
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from model import DailyStats, Detection, DetectionDetail, TrashCan, WasteType

# FastAPI 앱 인스턴스 (자동 문서화 포함)
app = FastAPI(title="Trash Detection API")


class BoxSchema(BaseModel):
    """바운딩 박스 좌표."""

    x1: float
    y1: float
    x2: float
    y2: float


class PredictionSchema(BaseModel):
    """YOLO 예측 결과의 단일 객체 스키마."""

    class_id: int
    class_name: str
    confidence: float
    box: BoxSchema


class DetectionIn(BaseModel):
    """탐지 이벤트 입력 스키마 (이미지 단위)."""

    trashcan_id: Optional[int] = None
    image_name: Optional[str] = Field(None, alias="filename")
    image_path: Optional[str] = Field(None, alias="saved_path")
    detected_at: Optional[datetime] = None
    total_objects: Optional[int] = Field(None, alias="object_count")
    predictions: List[PredictionSchema] = Field(default_factory=list, alias="objects")

    class Config:
        validate_by_name = True

    @model_validator(mode="before")
    def normalize_fields(cls, values: Dict) -> Dict:
        if "filename" not in values and "source_image" in values:
            values["filename"] = values["source_image"]
        if "saved_path" not in values and "image_path" in values:
            values["saved_path"] = values["image_path"]
        if "objects" not in values and "predictions" in values:
            values["objects"] = values["predictions"]
        return values


def get_db():
    """요청마다 DB 세션을 생성/종료하는 의존성."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_trashcan(db: Session, trashcan_id: Optional[int]) -> TrashCan:
    if trashcan_id is not None:
        trashcan = db.query(TrashCan).filter(TrashCan.trashcan_id == trashcan_id).one_or_none()
        if trashcan:
            return trashcan
        trashcan = TrashCan(trashcan_id=trashcan_id, trashcan_name=f"TrashCan {trashcan_id}")
        db.add(trashcan)
        db.flush()
        return trashcan
    trashcan = db.query(TrashCan).filter(TrashCan.trashcan_name == "UNKNOWN").one_or_none()
    if trashcan:
        return trashcan
    trashcan = TrashCan(trashcan_name="UNKNOWN", trashcan_city="UNKNOWN")
    db.add(trashcan)
    db.flush()
    return trashcan


def get_or_create_waste_type(db: Session, class_id: int, class_name: str) -> WasteType:
    waste_type = db.query(WasteType).filter(WasteType.waste_type_id == class_id).one_or_none()
    if waste_type:
        return waste_type
    waste_type = WasteType(waste_type_id=class_id, type_name=class_name)
    db.add(waste_type)
    db.flush()
    return waste_type

# 통계 갱신 주기 (분)
STATS_INTERVAL_MINUTES = 60
# 통계 데이터 조회 대기 일수
STATS_LAG_DAYS = 1


def upsert_daily_stats(
    db: Session,
    stats_date: date,
    trashcan_city: str,
    waste_type_id: int,
    detection_count: int,
) -> None:
    row = (
        db.query(DailyStats)
        .filter(
            DailyStats.stats_date == stats_date,
            DailyStats.trashcan_city == trashcan_city,
            DailyStats.waste_type_id == waste_type_id,
        )
        .one_or_none()
    )
    if row:
        row.detection_count = detection_count
    else:
        db.add(
            DailyStats(
                stats_date=stats_date,
                trashcan_city=trashcan_city,
                waste_type_id=waste_type_id,
                detection_count=detection_count,
            )
        )


def refresh_daily_stats(target_date: date) -> None:
    with SessionLocal() as db:
        rows = (
            db.query(TrashCan.trashcan_city, DetectionDetail.waste_type_id, func.count())
            .join(Detection, Detection.trashcan_id == TrashCan.trashcan_id)
            .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
            .filter(func.date(Detection.detected_at) == target_date)
            .group_by(TrashCan.trashcan_city, DetectionDetail.waste_type_id)
            .all()
        )
        for trashcan_city, waste_type_id, detection_count in rows:
            upsert_daily_stats(db, target_date, trashcan_city, waste_type_id, detection_count)
        db.commit()


async def stats_scheduler() -> None:
    while True:
        target_date = (datetime.utcnow() - timedelta(days=STATS_LAG_DAYS)).date()
        try:
            refresh_daily_stats(target_date)
        except Exception:
            # 스케줄러 실패가 서버를 죽이지 않도록 보호
            pass
        await asyncio.sleep(STATS_INTERVAL_MINUTES * 60)


@app.on_event("startup")
async def on_startup() -> None:
    """앱 시작 시 테이블 자동 생성 및 스케줄러 시작."""

    Base.metadata.create_all(bind=engine)
    app.state.stats_task = asyncio.create_task(stats_scheduler())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """스케줄러 종료."""

    task = getattr(app.state, "stats_task", None)
    if task:
        task.cancel()


@app.get("/health")
def health() -> dict:
    """헬스체크."""

    return {"status": "ok"}


@app.post("/detections")
def create_detection(payload: DetectionIn, db: Session = Depends(get_db)) -> dict:
    """탐지 이벤트를 저장하고 생성된 ID를 반환."""

    # 탐지 시각이 없으면 현재 시각으로 대체
    detected_at = payload.detected_at or datetime.utcnow()
    # total_objects가 없으면 predictions 길이로 계산
    total_objects = payload.total_objects
    if total_objects is None:
        total_objects = len(payload.predictions)

    trashcan = get_or_create_trashcan(db, payload.trashcan_id)

    # 이미지 단위 이벤트 저장
    detection = Detection(
        trashcan_id=trashcan.trashcan_id,
        image_name=payload.image_name,
        image_path=payload.image_path,
        detected_at=detected_at,
        object_count=total_objects,
    )
    db.add(detection)
    db.flush()

    # 예측 객체들을 개별로 저장
    for pred in payload.predictions:
        waste_type = get_or_create_waste_type(db, pred.class_id, pred.class_name)
        obj = DetectionDetail(
            detection_id=detection.detection_id,
            waste_type_id=waste_type.waste_type_id,
            confidence=pred.confidence,
            bbox_info={
                "x1": pred.box.x1,
                "y1": pred.box.y1,
                "x2": pred.box.x2,
                "y2": pred.box.y2,
            },
        )
        db.add(obj)

    # 트랜잭션 커밋
    db.commit()
    return {"detection_id": detection.detection_id, "total_objects": total_objects}


@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict:
    """전체 쓰레기 수 및 유형별 집계."""

    total_objects = db.query(func.count(DetectionDetail.detail_id)).scalar() or 0
    total_events = db.query(func.count(Detection.detection_id)).scalar() or 0
    type_rows = (
        db.query(WasteType.type_name, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, WasteType.waste_type_id == DetectionDetail.waste_type_id)
        .group_by(WasteType.type_name)
        .all()
    )
    return {
        "total_objects": total_objects,
        "total_events": total_events,
        "by_type": {name: count for name, count in type_rows},
    }


@app.get("/dashboard/stats")
def dashboard_stats(
    period: str = Query("week", pattern="^(week|month|year)$"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """주간/월간/연간 통계 조회."""

    today = datetime.utcnow().date()
    if start_date and end_date:
        start = start_date
        end = end_date
    else:
        if period == "month":
            start = today.replace(day=1)
        elif period == "year":
            start = date(today.year, 1, 1)
        else:
            start = today - timedelta(days=6)
        end = today

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    total_events = (
        db.query(func.count(Detection.detection_id))
        .filter(Detection.detected_at.between(start_dt, end_dt))
        .scalar()
        or 0
    )
    total_objects = (
        db.query(func.count(DetectionDetail.detail_id))
        .join(Detection, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.detected_at.between(start_dt, end_dt))
        .scalar()
        or 0
    )
    type_rows = (
        db.query(WasteType.type_name, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, WasteType.waste_type_id == DetectionDetail.waste_type_id)
        .join(Detection, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.detected_at.between(start_dt, end_dt))
        .group_by(WasteType.type_name)
        .all()
    )
    city_rows = (
        db.query(TrashCan.trashcan_city, func.count(DetectionDetail.detail_id))
        .join(Detection, Detection.trashcan_id == TrashCan.trashcan_id)
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.detected_at.between(start_dt, end_dt))
        .group_by(TrashCan.trashcan_city)
        .all()
    )

    return {
        "period": period,
        "start_date": start,
        "end_date": end,
        "total_events": total_events,
        "total_objects": total_objects,
        "by_type": {name: count for name, count in type_rows},
        "by_city": {city: count for city, count in city_rows},
    }


@app.get("/trashcans/collection-needed")
def collection_needed(
    status: Optional[str] = Query(None, pattern="^(포화|보통|여유|알수없음)$"),
    sort: str = Query("status", pattern="^(status|count)$"),
    window_days: int = Query(7, ge=1, le=365), # 수거 필요 쓰레기통 조회 기간 ex.최근 7일간 발생한 탐지횟수 통해 상태 계산
    # 쓰레기통 상태 계산 임계값
    full_threshold: int = Query(50, ge=1), # 포화 임계값
    medium_threshold: int = Query(20, ge=1), # 보통 임계값
    db: Session = Depends(get_db),
) -> dict:
    """탐지 이벤트 기반 수거 필요 쓰레기통 조회."""

    def compute_status(current: Optional[int]) -> str:
        if current is None:
            return "알수없음"
        elif current >= full_threshold:
            return "포화"
        elif current >= medium_threshold:
            return "보통"
        return "여유"

    cutoff = datetime.utcnow() - timedelta(days=window_days)
    volume_rows = (
        db.query(Detection.trashcan_id, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.detected_at >= cutoff)
        .group_by(Detection.trashcan_id)
        .all()
    )
    volume_map = {trashcan_id: count for trashcan_id, count in volume_rows}

    rows = db.query(TrashCan).all()
    result = []
    for row in rows:
        current_volume = volume_map.get(row.trashcan_id)
        state = compute_status(current_volume)
        if status and state != status:
            continue
        result.append(
            {
                "trashcan_id": row.trashcan_id,
                "trashcan_name": row.trashcan_name,
                "trashcan_city": row.trashcan_city,
                "detection_count": current_volume,
                "status": state,
                "window_days": window_days,
                "full_threshold": full_threshold,
                "medium_threshold": medium_threshold,
            }
        )

    status_order = {"포화": 0, "보통": 1, "여유": 2, "알수없음": 3}
    if sort == "count":
        result.sort(key=lambda item: (item["detection_count"] is None, -(item["detection_count"] or 0)))
    else:
        result.sort(
            key=lambda item: (
                status_order.get(item["status"], 9),
                -(item["detection_count"] or 0),
            )
        )
    return {"items": result}


@app.get("/trashcans/offline")
def offline_trashcans(
    stale_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict:
    """미연결 쓰레기통 및 간단 에러 상태 확인."""

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=stale_hours)
    rows = db.query(TrashCan).filter(TrashCan.is_online.is_(False)).all()
    items = []
    for row in rows:
        if row.last_connected_at is None:
            reason = "never_connected"
        elif row.last_connected_at < cutoff:
            reason = "stale_connection"
        else:
            reason = "offline"
        items.append(
            {
                "trashcan_id": row.trashcan_id,
                "trashcan_name": row.trashcan_name,
                "trashcan_city": row.trashcan_city,
                "last_connected_at": row.last_connected_at,
                "error_reason": reason,
            }
        )
    return {"items": items}
