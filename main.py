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

# 통계 갱신 주기 (분)
STATS_INTERVAL_MINUTES = 60
# 통계 데이터 조회 대기 일수
STATS_LAG_DAYS = 1


# =========================
# 입력 스키마
# =========================
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


class TrashCanIn(BaseModel):
    """쓰레기통 등록 입력 스키마."""

    trashcan_name: str
    trashcan_capacity: Optional[int] = None
    trashcan_city: Optional[str] = None
    address_detail: Optional[str] = None
    trashcan_latitude: Optional[float] = None
    trashcan_longitude: Optional[float] = None
    is_online: Optional[bool] = False


class TrashCanUpdate(BaseModel):
    """쓰레기통 수정 입력 스키마."""

    trashcan_name: Optional[str] = None
    trashcan_city: Optional[str] = None
    address_detail: Optional[str] = None
    trashcan_capacity: Optional[int] = None
    trashcan_latitude: Optional[float] = None
    trashcan_longitude: Optional[float] = None
    is_online: Optional[bool] = None


class WasteTypeIn(BaseModel):
    """쓰레기 종류 등록 입력 스키마."""

    type_name: str


# =========================
# DB 헬퍼
# =========================
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
            if trashcan.is_deleted:
                trashcan.is_deleted = False
                db.flush()
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


# =========================
# 일별 통계 스케줄러
# =========================
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


# =========================
# API 엔드포인트
# =========================
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


@app.post("/trashcans")
def create_trashcan(payload: TrashCanIn, db: Session = Depends(get_db)) -> dict:
    """쓰레기통 등록."""

    trashcan = TrashCan(
        trashcan_name=payload.trashcan_name,
        trashcan_capacity=payload.trashcan_capacity,
        trashcan_city=payload.trashcan_city,
        address_detail=payload.address_detail,
        trashcan_latitude=payload.trashcan_latitude,
        trashcan_longitude=payload.trashcan_longitude,
        is_online=payload.is_online,
    )
    db.add(trashcan)
    db.commit()
    db.refresh(trashcan)
    return {"trashcan_id": trashcan.trashcan_id}


@app.get("/trashcans")
def list_trashcans(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    window_days: int = Query(7, ge=1, le=365),
    full_threshold: int = Query(50, ge=1),
    medium_threshold: int = Query(20, ge=1),
    sort: str = Query(
        "total_desc",
        pattern="^(total_desc|total_asc|capacity_remaining_desc|capacity_remaining_asc|status_desc|status_asc)$",
    ),
    is_online: Optional[bool] = Query(None),
    city: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> List[dict]:
    """쓰레기통 검색/정렬 목록 조회 (offset 기반 페이지네이션)."""

    def compute_status(current: Optional[int]) -> str:
        if current is None:
            return "unknown"
        if current >= full_threshold:
            return "full"
        if current >= medium_threshold:
            return "medium"
        return "low"

    status_order = {"full": 0, "medium": 1, "low": 2, "unknown": 3}

    total_rows = (
        db.query(Detection.trashcan_id, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .group_by(Detection.trashcan_id)
        .all()
    )
    total_map = {trashcan_id: count for trashcan_id, count in total_rows}

    cutoff = datetime.utcnow() - timedelta(days=window_days)
    window_rows = (
        db.query(Detection.trashcan_id, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.detected_at >= cutoff)
        .group_by(Detection.trashcan_id)
        .all()
    )
    window_map = {trashcan_id: count for trashcan_id, count in window_rows}

    rows = db.query(TrashCan).filter(TrashCan.is_deleted.is_(False)).all()
    items = []
    for row in rows:
        if is_online is not None and row.is_online is not is_online:
            continue
        if city:
            if row.trashcan_city is None or city.lower() not in row.trashcan_city.lower():
                continue
        if name and (row.trashcan_name is None or name.lower() not in row.trashcan_name.lower()):
            continue
        total_objects = total_map.get(row.trashcan_id, 0)
        current_objects = window_map.get(row.trashcan_id, 0)
        capacity_remaining = None
        if row.trashcan_capacity is not None:
            capacity_remaining = row.trashcan_capacity - current_objects
        items.append(
            {
                "trashcan_id": row.trashcan_id,
                "trashcan_name": row.trashcan_name,
                "total_objects": total_objects,
                "current_objects": current_objects,
                "capacity_remaining": capacity_remaining,
                "trashcan_city": row.trashcan_city,
                "address_detail": row.address_detail,
                "is_online": row.is_online,
                "last_connected_at": row.last_connected_at,
                "status": compute_status(current_objects),
            }
        )
    if sort == "total_asc":
        items.sort(key=lambda item: item["total_objects"])
    elif sort == "capacity_remaining_desc":
        items.sort(
            key=lambda item: (
                item["capacity_remaining"] is None,
                -(item["capacity_remaining"] or 0),
            )
        )
    elif sort == "capacity_remaining_asc":
        items.sort(key=lambda item: (item["capacity_remaining"] is None, item["capacity_remaining"] or 0))
    elif sort == "status_desc":
        items.sort(key=lambda item: (status_order.get(item["status"], 9), -(item["current_objects"] or 0)))
    elif sort == "status_asc":
        items.sort(key=lambda item: (status_order.get(item["status"], 9), item["current_objects"] or 0))
    else:
        items.sort(key=lambda item: -item["total_objects"])
    return items[offset : offset + limit]


@app.get("/trashcans/locations")
def trashcan_locations(
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    city: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """지도용 쓰레기통 위치 조회."""

    query = (
        db.query(TrashCan)
        .filter(
            TrashCan.is_deleted.is_(False),
            TrashCan.trashcan_latitude.is_not(None),
            TrashCan.trashcan_longitude.is_not(None),
        )
    )
    rows = query.all()
    items = []
    for row in rows:
        if city:
            if row.trashcan_city is None or city.lower() not in row.trashcan_city.lower():
                continue
        if name and (row.trashcan_name is None or name.lower() not in row.trashcan_name.lower()):
            continue
        items.append(
            {
                "trashcan_id": row.trashcan_id,
                "trashcan_name": row.trashcan_name,
                "trashcan_city": row.trashcan_city,
                "address_detail": row.address_detail,
                "trashcan_latitude": row.trashcan_latitude,
                "trashcan_longitude": row.trashcan_longitude,
            }
        )
    return {"items": items[offset : offset + limit]}


@app.patch("/trashcans/{trashcan_id}")
def update_trashcan(trashcan_id: int, payload: TrashCanUpdate, db: Session = Depends(get_db)) -> dict:
    """쓰레기통 이름/주소 수정."""

    trashcan = (
        db.query(TrashCan)
        .filter(TrashCan.trashcan_id == trashcan_id, TrashCan.is_deleted.is_(False))
        .one_or_none()
    )
    if not trashcan:
        return {"updated": False, "reason": "not_found"}

    if payload.trashcan_name is not None:
        trashcan.trashcan_name = payload.trashcan_name
    if payload.trashcan_city is not None:
        trashcan.trashcan_city = payload.trashcan_city
    if payload.address_detail is not None:
        trashcan.address_detail = payload.address_detail
    if payload.trashcan_capacity is not None:
        trashcan.trashcan_capacity = payload.trashcan_capacity
    if payload.trashcan_latitude is not None:
        trashcan.trashcan_latitude = payload.trashcan_latitude
    if payload.trashcan_longitude is not None:
        trashcan.trashcan_longitude = payload.trashcan_longitude
    if payload.is_online is not None:
        trashcan.is_online = payload.is_online

    db.commit()
    return {
        "updated": True,
        "trashcan_id": trashcan.trashcan_id,
        "trashcan_name": trashcan.trashcan_name,
        "trashcan_city": trashcan.trashcan_city,
        "address_detail": trashcan.address_detail,
        "trashcan_capacity": trashcan.trashcan_capacity,
        "trashcan_latitude": trashcan.trashcan_latitude,
        "trashcan_longitude": trashcan.trashcan_longitude,
        "is_online": trashcan.is_online,
    }


@app.post("/trashcans/{trashcan_id}")
def update_trashcan_post(trashcan_id: int, payload: TrashCanUpdate, db: Session = Depends(get_db)) -> dict:
    """쓰레기통 수정 (POST 지원)."""

    return update_trashcan(trashcan_id, payload, db)


@app.delete("/trashcans/{trashcan_id}")
def delete_trashcan(trashcan_id: int, db: Session = Depends(get_db)) -> dict:
    """쓰레기통 삭제(소프트 삭제)."""

    trashcan = db.query(TrashCan).filter(TrashCan.trashcan_id == trashcan_id).one_or_none()
    if not trashcan:
        return {"deleted": False, "reason": "not_found"}
    if trashcan.is_deleted:
        return {"deleted": True, "already_deleted": True}
    trashcan.is_deleted = True
    trashcan.is_online = False
    db.commit()
    return {"deleted": True, "soft_deleted": True}


@app.post("/trashcans/{trashcan_id}/restore")
def restore_trashcan(trashcan_id: int, db: Session = Depends(get_db)) -> dict:
    """쓰레기통 복구(소프트 삭제 복구)."""

    trashcan = db.query(TrashCan).filter(TrashCan.trashcan_id == trashcan_id).one_or_none()
    if not trashcan:
        return {"restored": False, "reason": "not_found"}
    if not trashcan.is_deleted:
        return {"restored": True, "already_active": True}
    trashcan.is_deleted = False
    db.commit()
    return {"restored": True}


@app.get("/trashcans/{trashcan_id}/summary")
def trashcan_summary(
    trashcan_id: int,
    window_days: int = Query(7, ge=1, le=365),
    full_threshold: int = Query(50, ge=1),
    medium_threshold: int = Query(20, ge=1),
    db: Session = Depends(get_db),
) -> dict:
    """쓰레기통별 종류 통계 및 여유공간 요약."""

    def compute_status(current: Optional[int]) -> str:
        if current is None:
            return "unknown"
        if current >= full_threshold:
            return "full"
        if current >= medium_threshold:
            return "medium"
        return "low"

    trashcan = (
        db.query(TrashCan)
        .filter(TrashCan.trashcan_id == trashcan_id, TrashCan.is_deleted.is_(False))
        .one_or_none()
    )
    if not trashcan:
        return {"ok": False, "reason": "not_found"}

    total_objects = (
        db.query(func.count(DetectionDetail.detail_id))
        .join(Detection, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.trashcan_id == trashcan_id)
        .scalar()
        or 0
    )
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    current_objects = (
        db.query(func.count(DetectionDetail.detail_id))
        .join(Detection, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.trashcan_id == trashcan_id, Detection.detected_at >= cutoff)
        .scalar()
        or 0
    )
    capacity_remaining = None
    if trashcan.trashcan_capacity is not None:
        capacity_remaining = trashcan.trashcan_capacity - current_objects

    type_rows = (
        db.query(WasteType.type_name, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, WasteType.waste_type_id == DetectionDetail.waste_type_id)
        .join(Detection, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.trashcan_id == trashcan_id)
        .group_by(WasteType.type_name)
        .all()
    )

    return {
        "trashcan_id": trashcan.trashcan_id,
        "trashcan_name": trashcan.trashcan_name,
        "trashcan_city": trashcan.trashcan_city,
        "address_detail": trashcan.address_detail,
        "is_online": trashcan.is_online,
        "last_connected_at": trashcan.last_connected_at,
        "total_objects": total_objects,
        "current_objects": current_objects,
        "capacity_remaining": capacity_remaining,
        "status": compute_status(current_objects),
        "by_type": {name: count for name, count in type_rows},
    }


@app.post("/trashcans/{trashcan_id}/connection-test")
def trashcan_connection_test(trashcan_id: int, db: Session = Depends(get_db)) -> dict:
    """쓰레기통 연결 상태 점검(현재 상태 기반)."""

    trashcan = (
        db.query(TrashCan)
        .filter(TrashCan.trashcan_id == trashcan_id, TrashCan.is_deleted.is_(False))
        .one_or_none()
    )
    if not trashcan:
        return {"ok": False, "reason": "not_found"}

    tested_at = datetime.utcnow()
    result = "online" if trashcan.is_online else "offline"
    if trashcan.is_online:
        trashcan.last_connected_at = tested_at
        db.commit()
    return {
        "trashcan_id": trashcan.trashcan_id,
        "is_online": trashcan.is_online,
        "last_connected_at": trashcan.last_connected_at,
        "tested_at": tested_at,
        "result": result,
    }


@app.get("/detections/details")
def detection_details(
    waste_type: str = Query("전체"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """쓰레기 종류별 상세(사진/일시) 조회."""

    type_map = {
        "전체": None,
        "all": None,
        "플라스틱": "Plastic",
        "유리병": "Glass Bottle",
        "캔": "Can",
        "스티로폼": "Styrofoam",
        "plastic": "Plastic",
        "glass bottle": "Glass Bottle",
        "can": "Can",
        "styrofoam": "Styrofoam",
    }
    normalized = type_map.get(waste_type, waste_type)

    query = (
        db.query(
            DetectionDetail.detail_id,
            WasteType.type_name,
            Detection.image_name,
            Detection.image_path,
            Detection.detected_at,
            Detection.trashcan_id,
        )
        .join(Detection, DetectionDetail.detection_id == Detection.detection_id)
        .join(WasteType, WasteType.waste_type_id == DetectionDetail.waste_type_id)
        .order_by(Detection.detected_at.desc())
    )
    if normalized:
        query = query.filter(WasteType.type_name == normalized)

    rows = query.offset(offset).limit(limit).all()
    items = []
    for detail_id, type_name, image_name, image_path, detected_at, trashcan_id in rows:
        items.append(
            {
                "detail_id": detail_id,
                "waste_type": type_name,
                "image_name": image_name,
                "image_path": image_path,
                "detected_at": detected_at,
                "trashcan_id": trashcan_id,
            }
        )
    return {"items": items}


@app.post("/waste-types")
def create_waste_type(payload: WasteTypeIn, db: Session = Depends(get_db)) -> dict:
    """쓰레기 종류 등록."""

    existing = db.query(WasteType).filter(WasteType.type_name == payload.type_name).one_or_none()
    if existing:
        return {"waste_type_id": existing.waste_type_id, "type_name": existing.type_name}
    waste_type = WasteType(type_name=payload.type_name)
    db.add(waste_type)
    db.commit()
    db.refresh(waste_type)
    return {"waste_type_id": waste_type.waste_type_id, "type_name": waste_type.type_name}


@app.delete("/waste-types/{waste_type_id}")
def delete_waste_type(waste_type_id: int, db: Session = Depends(get_db)) -> dict:
    """쓰레기 종류 삭제."""

    waste_type = db.query(WasteType).filter(WasteType.waste_type_id == waste_type_id).one_or_none()
    if not waste_type:
        return {"deleted": False, "reason": "not_found"}
    if waste_type.detection_details:
        return {"deleted": False, "reason": "in_use"}
    db.delete(waste_type)
    db.commit()
    return {"deleted": True}


@app.post("/waste-types/seed")
def seed_waste_types(
    types: List[str] = Query(..., description="쉼표 없이 여러 번 전달"),
    db: Session = Depends(get_db),
) -> dict:
    """쓰레기 종류 초기 데이터 등록."""

    created = 0
    skipped = 0
    for name in types:
        exists = db.query(WasteType).filter(WasteType.type_name == name).one_or_none()
        if exists:
            skipped += 1
            continue
        db.add(WasteType(type_name=name))
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


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


@app.get("/dashboard/summary/trashcans")
def dashboard_summary_by_trashcan(db: Session = Depends(get_db)) -> dict:
    """쓰레기통별 요약 집계."""

    events_rows = (
        db.query(Detection.trashcan_id, func.count(Detection.detection_id))
        .group_by(Detection.trashcan_id)
        .all()
    )
    objects_rows = (
        db.query(Detection.trashcan_id, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .group_by(Detection.trashcan_id)
        .all()
    )
    type_rows = (
        db.query(Detection.trashcan_id, WasteType.type_name, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .join(WasteType, WasteType.waste_type_id == DetectionDetail.waste_type_id)
        .group_by(Detection.trashcan_id, WasteType.type_name)
        .all()
    )

    items_map: Dict[int, Dict] = {}
    for trashcan_id, count in events_rows:
        items_map.setdefault(trashcan_id, {"total_events": 0, "total_objects": 0, "by_type": {}})
        items_map[trashcan_id]["total_events"] = count
    for trashcan_id, count in objects_rows:
        items_map.setdefault(trashcan_id, {"total_events": 0, "total_objects": 0, "by_type": {}})
        items_map[trashcan_id]["total_objects"] = count
    for trashcan_id, type_name, count in type_rows:
        items_map.setdefault(trashcan_id, {"total_events": 0, "total_objects": 0, "by_type": {}})
        items_map[trashcan_id]["by_type"][type_name] = count

    trashcans = db.query(TrashCan).filter(TrashCan.is_deleted.is_(False)).all()
    items = []
    for trashcan in trashcans:
        summary = items_map.get(
            trashcan.trashcan_id,
            {"total_events": 0, "total_objects": 0, "by_type": {}},
        )
        items.append(
            {
                "trashcan_id": trashcan.trashcan_id,
                "trashcan_name": trashcan.trashcan_name,
                "trashcan_city": trashcan.trashcan_city,
                "total_events": summary["total_events"],
                "total_objects": summary["total_objects"],
                "by_type": summary["by_type"],
            }
        )

    return {"items": items}


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
        response_period = "custom"
    else:
        if period == "month":
            start = today.replace(day=1)
        elif period == "year":
            start = date(today.year, 1, 1)
        else:
            start = today - timedelta(days=6)
        end = today
        response_period = period

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
        "period": response_period,
        "start_date": start,
        "end_date": end,
        "total_events": total_events,
        "total_objects": total_objects,
        "by_type": {name: count for name, count in type_rows},
        "by_city": {city: count for city, count in city_rows},
    }


@app.get("/trashcans/collection-needed")
def collection_needed(
    status: Optional[str] = Query(None, pattern="^(full|medium|low|unknown)$"),
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
            return "unknown"
        if current >= full_threshold:
            return "full"
        if current >= medium_threshold:
            return "medium"
        return "low"

    cutoff = datetime.utcnow() - timedelta(days=window_days)
    volume_rows = (
        db.query(Detection.trashcan_id, func.count(DetectionDetail.detail_id))
        .join(DetectionDetail, DetectionDetail.detection_id == Detection.detection_id)
        .filter(Detection.detected_at >= cutoff)
        .group_by(Detection.trashcan_id)
        .all()
    )
    volume_map = {trashcan_id: count for trashcan_id, count in volume_rows}

    rows = db.query(TrashCan).filter(TrashCan.is_deleted.is_(False)).all()
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

    status_order = {"full": 0, "medium": 1, "low": 2, "unknown": 3}
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
    rows = (
        db.query(TrashCan)
        .filter(TrashCan.is_online.is_(False), TrashCan.is_deleted.is_(False))
        .all()
    )
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
