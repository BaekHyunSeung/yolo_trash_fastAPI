# Backend 문서

이 문서는 현재 백엔드 구현 내용을 기준으로 정리한 운영/연동 가이드입니다.

## 1) 개요
- FastAPI 기반 REST API
- YOLO 탐지 결과 저장 및 대시보드 통계 제공
- 스케줄러로 일별 통계(DailyStats) 자동 갱신

## 2) 구성 파일
- `database.py`: DB 연결/세션/베이스 설정
- `model.py`: DB 모델 정의
- `main.py`: API 및 스케줄러 로직

## 3) 설치
```bash
pip install fastapi uvicorn sqlalchemy pymysql pydantic cryptography
```

## 4) DB 설정
`secrets.json`에 MySQL 접속 정보를 저장합니다.

예시:
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

## 5) 실행
```bash
uvicorn main:app --reload
```

## 6) API 엔드포인트

### 6.1 헬스체크
`GET /health`

응답:
```json
{ "status": "ok" }
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health"
```

### 6.2 탐지 결과 저장
`POST /detections`

입력 예시(`valid-2.json` 형식):
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

PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/detections" -Method Post -ContentType "application/json" -InFile "C:\Users\bhs20\OneDrive\바탕 화면\YOLO 데이터\valid-2.json"
```

### 6.2.A 쓰레기 종류별 상세 조회 (사진/일시)
`GET /detections/details`

쿼리 파라미터:
- `waste_type` (기본 전체): `전체|플라스틱|유리병|캔|스티로폼` 또는 영문(`Plastic|Glass Bottle|Can|Styrofoam`)
- `offset` (기본 0)
- `limit` (기본 50, 최대 200)

응답 예시:
```json
{
  "items": [
    {
      "detail_id": 10,
      "waste_type": "Plastic",
      "image_name": "valid-2.jpg",
      "image_path": "detect_img/valid-2.jpg",
      "detected_at": "2026-01-26T08:30:00",
      "trashcan_id": 3
    }
  ]
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/detections/details?waste_type=전체&offset=0&limit=20"
Invoke-RestMethod "http://127.0.0.1:8000/detections/details?waste_type=플라스틱&offset=0&limit=20"
```

### 6.2.1 쓰레기통 등록
`POST /trashcans`

입력 예시:
```json
{
  "trashcan_name": "TrashCan 1",
  "trashcan_capacity": 100,
  "trashcan_city": "Seoul",
  "address_detail": "Sample Address",
  "trashcan_latitude": 37.5665,
  "trashcan_longitude": 126.9780,
  "is_online": true
}
```

응답 예시:
```json
{ "trashcan_id": 1 }
```

PowerShell:
```powershell
$body = @{
  trashcan_name = "TrashCan 1"
  trashcan_capacity = 100
  trashcan_city = "Seoul"
  address_detail = "Sample Address"
  trashcan_latitude = 37.5665
  trashcan_longitude = 126.9780
  is_online = $true
} | ConvertTo-Json
Invoke-RestMethod "http://127.0.0.1:8000/trashcans" -Method Post -ContentType "application/json" -Body $body
```

### 6.2.1.A 쓰레기통 목록 조회
`GET /trashcans`

쿼리 파라미터:
- `offset` (기본 0): 페이지 시작 위치
- `limit` (기본 50): 페이지 크기 (최대 200)
- `window_days` (기본 7): 포화상태 계산에 사용하는 기간
- `full_threshold` (기본 50): 포화 기준 탐지 횟수
- `medium_threshold` (기본 20): 보통 기준 탐지 횟수
- `sort` (기본 total_desc): `total_desc|total_asc|capacity_remaining_desc|capacity_remaining_asc|status_desc|status_asc`
- `is_online`: `true|false`로 연결 상태 필터
- `city`: 도시 필터 (부분 포함, 대소문자 무시)
- `name`: 쓰레기통 이름 검색 (부분 포함, 대소문자 무시)

응답 예시:
```json
[
  {
    "trashcan_id": 1,
    "trashcan_name": "TrashCan 1",
    "total_objects": 120,
    "current_objects": 18,
    "capacity_remaining": 82,
    "trashcan_city": "Seoul",
    "address_detail": "Sample Address",
    "is_online": true,
    "last_connected_at": "2026-01-25T10:20:00",
    "status": "medium"
  }
]
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans?offset=0&limit=20&window_days=7&full_threshold=50&medium_threshold=20&sort=total_desc&city=Seoul&name=TrashCan&is_online=true"
```

### 6.2.1.A-1 지도용 위치 조회
`GET /trashcans/locations`

쿼리 파라미터:
- `offset` (기본 0)
- `limit` (기본 200, 최대 500)
- `city`: 도시 필터 (부분 포함, 대소문자 무시)
- `name`: 쓰레기통 이름 검색 (부분 포함, 대소문자 무시)

응답 예시:
```json
{
  "items": [
    {
      "trashcan_id": 3,
      "trashcan_name": "TrashCan 3",
      "trashcan_city": "suwon",
      "address_detail": "Sample Address",
      "trashcan_latitude": 37.5665,
      "trashcan_longitude": 126.9780
    }
  ]
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/locations?offset=0&limit=200"
```

### 6.2.1.B 쓰레기통 수정 (이름/주소/용량/좌표/연결상태)
`PATCH /trashcans/{trashcan_id}` 또는 `POST /trashcans/{trashcan_id}`

입력 예시:
```json
{
  "trashcan_name": "TrashCan 3",
  "trashcan_city": "suwon",
  "address_detail": "Sample Address",
  "trashcan_capacity": 120,
  "trashcan_latitude": 37.5665,
  "trashcan_longitude": 126.9780,
  "is_online": true
}
```

응답 예시:
```json
{
  "updated": true,
  "trashcan_id": 3,
  "trashcan_name": "TrashCan 3",
  "trashcan_city": "suwon",
  "address_detail": "Sample Address",
  "trashcan_capacity": 120,
  "trashcan_latitude": 37.5665,
  "trashcan_longitude": 126.9780,
  "is_online": true
}
```

PowerShell:
```powershell
$body = @{
  trashcan_name = "TrashCan 3"
  trashcan_city = "suwon"
  address_detail = "Sample Address"
  trashcan_capacity = 120
  trashcan_latitude = 37.5665
  trashcan_longitude = 126.9780
  is_online = $true
} | ConvertTo-Json
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/3" -Method Patch -ContentType "application/json" -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/3" -Method Post -ContentType "application/json" -Body $body
```

### 6.2.1.1 쓰레기통 삭제
`DELETE /trashcans/{trashcan_id}`

응답 예시:
```json
{ "deleted": true, "soft_deleted": true }
```
이미 삭제된 경우:
```json
{ "deleted": true, "already_deleted": true }
```
실패 예시:
```json
{ "deleted": false, "reason": "not_found" }
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/1" -Method Delete
```

### 6.2.1.2 쓰레기통 복구
`POST /trashcans/{trashcan_id}/restore`

응답 예시:
```json
{ "restored": true }
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/1/restore" -Method Post
```

### 6.2.1.C 쓰레기통 요약 (종류별 통계/여유공간)
`GET /trashcans/{trashcan_id}/summary`

쿼리 파라미터:
- `window_days` (기본 7): 포화상태 계산에 사용하는 기간
- `full_threshold` (기본 50): 포화 기준 탐지 횟수
- `medium_threshold` (기본 20): 보통 기준 탐지 횟수

응답 예시:
```json
{
  "trashcan_id": 3,
  "trashcan_name": "TrashCan 3",
  "trashcan_city": "suwon",
  "address_detail": "??? ??? ???",
  "is_online": true,
  "last_connected_at": null,
  "total_objects": 2,
  "current_objects": 2,
  "capacity_remaining": 98,
  "status": "low",
  "by_type": { "Plastic": 2 }
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/3/summary?window_days=7&full_threshold=50&medium_threshold=20"
```

### 6.2.1.D 쓰레기통 연결 테스트
`POST /trashcans/{trashcan_id}/connection-test`

설명:
- 현재 `is_online` 상태를 기준으로 결과 반환
- 온라인이면 `last_connected_at`을 테스트 시각으로 갱신

응답 예시:
```json
{
  "trashcan_id": 3,
  "is_online": true,
  "last_connected_at": null,
  "tested_at": "2026-01-26T09:00:00",
  "result": "online"
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/3/connection-test" -Method Post
```

### 6.2.2 쓰레기 종류 등록
`POST /waste-types`

입력 예시:
```json
{ "type_name": "Plastic" }
```

응답 예시:
```json
{ "waste_type_id": 1, "type_name": "Plastic" }
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/waste-types" -Method Post -ContentType "application/json" -Body '{"type_name":"Plastic"}'
```

### 6.2.2.1 쓰레기 종류 삭제
`DELETE /waste-types/{waste_type_id}`

응답 예시:
```json
{ "deleted": true }
```
실패 예시:
```json
{ "deleted": false, "reason": "in_use" }
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/waste-types/1" -Method Delete
```

### 6.2.3 쓰레기 종류 초기 데이터 등록
`POST /waste-types/seed?types=Plastic&types=PET%20Bottle&types=Can&types=Styrofoam`

응답 예시:
```json
{ "created": 4, "skipped": 0 }
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/waste-types/seed?types=Plastic&types=PET%20Bottle&types=Can&types=Styrofoam" -Method Post
```

### 6.3 대시보드 요약
`GET /dashboard/summary`

응답 예시:
```json
{
  "total_objects": 2,
  "total_events": 1,
  "by_type": { "Plastic": 1, "PET Bottle": 1 }
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/summary"
```

### 6.3.1 쓰레기통별 요약
`GET /dashboard/summary/trashcans`

응답 예시:
```json
{
  "items": [
    {
      "trashcan_id": 1,
      "trashcan_name": "TrashCan 1",
      "trashcan_city": "Seoul",
      "total_events": 1,
      "total_objects": 2,
      "by_type": { "Plastic": 1, "PET Bottle": 1 }
    }
  ]
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/summary/trashcans"
```

### 6.4 기간 통계
`GET /dashboard/stats?period=week|month|year`
또는
`GET /dashboard/stats?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

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

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/stats?period=week"
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/stats?start_date=2026-01-20&end_date=2026-01-26"
```

### 6.5 수거 필요 쓰레기통 조회 (탐지 횟수 기반)
`GET /trashcans/collection-needed`

쿼리 파라미터:
- `window_days` (기본 7): 최근 며칠 동안의 탐지 횟수로 상태 계산
- `full_threshold` (기본 50): 포화 기준 탐지 횟수
- `medium_threshold` (기본 20): 보통 기준 탐지 횟수
- `status`: `full|medium|low|unknown`
- `sort`: `status|count`

응답 예시:
```json
{
  "items": [
    {
      "trashcan_id": 1,
      "trashcan_name": "TrashCan 1",
      "trashcan_city": "Seoul",
      "detection_count": 42,
      "status": "medium",
      "window_days": 7,
      "full_threshold": 50,
      "medium_threshold": 20
    }
  ]
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/collection-needed?window_days=7&full_threshold=50&medium_threshold=20&sort=status"
```

### 6.6 미연결 쓰레기통 조회
`GET /trashcans/offline?stale_hours=24`

응답 예시:
```json
{
  "items": [
    {
      "trashcan_id": 1,
      "trashcan_name": "TrashCan 1",
      "trashcan_city": "Seoul",
      "last_connected_at": "2026-01-25T10:20:00",
      "error_reason": "stale_connection"
    }
  ]
}
```

PowerShell:
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/offline?stale_hours=24"
```

## 7) 스케줄러 (일별 통계 갱신)
- 실행 주기: 60분 (`STATS_INTERVAL_MINUTES`)
- 기준 날짜: 전날 (`STATS_LAG_DAYS = 1`)
- 대상: `DailyStats`

집계 기준:
- `Detection.detected_at` 날짜 기준
- `TrashCan.trashcan_city`, `DetectionDetail.waste_type_id` 기준 그룹핑
- 기존 통계가 있으면 업데이트, 없으면 삽입

## 8) 주의사항
- MySQL 인증이 `caching_sha2_password`일 경우 `cryptography` 패키지가 필요합니다.
- `trashcan_id`가 없는 입력은 `UNKNOWN` 쓰레기통으로 자동 매핑됩니다.
- `WasteType`은 `class_id` 기준으로 자동 생성됩니다.
- 쓰레기통 삭제는 `is_deleted`로 처리되는 소프트 삭제입니다.

## 9) 자동 문서화
- `http://localhost:8000/docs`

## 10) Request/Response 상세 문서
- `REQUEST_RESPONSE.md`에 모든 API의 요청/응답과 출력 예시를 정리했습니다.
