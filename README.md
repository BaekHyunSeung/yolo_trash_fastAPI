# Trash Detection API 문서

YOLO 객체 탐지 결과(`valid-2.json`)를 MySQL에 저장하기 위한 최소 FastAPI 백엔드입니다.

## 1) 구성 요약
- `database.py`: DB 연결/세션/베이스 설정
- `model.py`: 쓰레기통/탐지/통계 모델
- `main.py`: FastAPI 앱 + 대시보드 API

## 2) 설치
```bash
pip install fastapi uvicorn sqlalchemy pymysql pydantic cryptography
```

## 3) DB 설정
`secrets.json`에 MySQL 접속 정보를 저장합니다.

예시(`secrets.json`):
```json
{
  "host": "localhost",
  "port": 3306,
  "user": "root",
  "password": "password",
  "db_name": "yolo_trash",
  "charset": "utf8mb4"
}
```

## 4) 실행
```bash
uvicorn main:app --reload
```

## 5) API

### 헬스체크
`GET /health`

응답:
```json
{ "status": "ok" }
```

### 탐지 결과 저장
`POST /detections`

요청 예시:
```json
{
  "trashcan_id": 1,
  "filename": "valid-2.jpg",
  "saved_path": "detect_img/valid-2.jpg",
  "object_count": 2,
  "objects": [
    {
      "class_id": 2,
      "class_name": "Plastic",
      "confidence": 0.905,
      "box": { "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0 }
    }
  ]
}
```

응답 예시:
```json
{ "detection_id": 1, "total_objects": 2 }
```

### 대시보드 요약
`GET /dashboard/summary`

응답 예시:
```json
{
  "total_objects": 2,
  "total_events": 1,
  "by_type": { "Plastic": 1, "PET Bottle": 1 }
}
```

### 기간 통계
`GET /dashboard/stats?period=week|month|year`
또는
`GET /dashboard/stats?start_date=2026-01-01&end_date=2026-01-31`

응답 예시:
```json
{
  "period": "custom",
  "start_date": "2026-01-20",
  "end_date": "2026-01-26",
  "total_events": 1,
  "total_objects": 2,
  "by_type": { "Plastic": 1, "PET Bottle": 1 },
  "by_city": { "UNKNOWN": 2 }
}
```

### 수거 필요 쓰레기통 조회
`GET /trashcans/collection-needed?window_days=7&full_threshold=50&medium_threshold=20&status=full&sort=status`

### 미연결 쓰레기통 조회
`GET /trashcans/offline?stale_hours=24`

### 쓰레기통 목록/검색
`GET /trashcans?offset=0&limit=20&sort=total_desc&city=Seoul&name=TrashCan&is_online=true`

### 쓰레기통 위치(지도)
`GET /trashcans/locations?offset=0&limit=200`

### 쓰레기통 수정
`PATCH /trashcans/{trashcan_id}` 또는 `POST /trashcans/{trashcan_id}`

### 쓰레기통 삭제/복구
`DELETE /trashcans/{trashcan_id}`
`POST /trashcans/{trashcan_id}/restore`

### 탐지 상세(사진/일시)
`GET /detections/details?waste_type=전체&offset=0&limit=20`

## 6) 테이블 구조

### TrashCan
- 쓰레기통 기본 정보
- 주요 컬럼: `trashcan_id`, `trashcan_city`, `trashcan_capacity`, `is_online`, `is_deleted`

### WasteType
- 쓰레기 종류 마스터
- 주요 컬럼: `waste_type_id`, `type_name`

### Detection
- 이미지 단위 탐지 이벤트
- 주요 컬럼: `trashcan_id`, `image_name`, `image_path`, `detected_at`, `object_count`

### Detection_detail
- 개별 객체 탐지 결과
- 주요 컬럼: `detection_id`, `waste_type_id`, `confidence`, `bbox_info`

### DailyStats
- 일별 통계
- 주요 컬럼: `stats_date`, `trashcan_city`, `waste_type_id`, `detection_count`

## 7) 참고
- 자동 문서화: `http://localhost:8000/docs`
