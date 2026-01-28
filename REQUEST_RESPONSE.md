# Request / Response 상세 문서

이 문서는 모든 API의 요청/응답과 출력 예시를 정리한 문서입니다.

## 1) 헬스체크
**Request**: `GET /health`

**Response 예시**
```json
{ "status": "ok" }
```

## 2) 탐지 결과 저장
**Request**: `POST /detections`

**Body 예시**
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

**Response 예시**
```json
{ "detection_id": 1, "total_objects": 2 }
```

## 2-1) 쓰레기 종류별 상세 조회 (사진/일시)
**Request**: `GET /detections/details`

**Query**
- `waste_type` (기본 전체): `전체|플라스틱|유리병|캔|스티로폼` 또는 영문(`Plastic|Glass Bottle|Can|Styrofoam`)
- `offset` (기본 0)
- `limit` (기본 50, 최대 200)

**Response 예시**
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

## 3) 쓰레기통 등록
**Request**: `POST /trashcans`

**Body 예시**
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

**Response 예시**
```json
{ "trashcan_id": 1 }
```

## 4) 쓰레기통 목록 조회
**Request**: `GET /trashcans`

**Query**
- `offset` (기본 0)
- `limit` (기본 50, 최대 200)
- `window_days` (기본 7)
- `full_threshold` (기본 50)
- `medium_threshold` (기본 20)
- `sort` (기본 total_desc): `total_desc|total_asc|capacity_remaining_desc|capacity_remaining_asc|status_desc|status_asc`
- `is_online`: `true|false`
- `city`: 도시 필터 (부분 포함, 대소문자 무시)
- `name`: 쓰레기통 이름 검색 (부분 포함, 대소문자 무시)

**Response 예시**
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

## 4-0) 지도용 위치 조회
**Request**: `GET /trashcans/locations`

**Query**
- `offset` (기본 0)
- `limit` (기본 200, 최대 500)
- `city`: 도시 필터 (부분 포함, 대소문자 무시)
- `name`: 쓰레기통 이름 검색 (부분 포함, 대소문자 무시)

**Response 예시**
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

## 4-1) 쓰레기통 수정 (이름/주소/용량/좌표/연결상태)
**Request**: `PATCH /trashcans/{trashcan_id}` 또는 `POST /trashcans/{trashcan_id}`

**Body 예시**
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

**Response 예시**
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

## 5) 쓰레기통 삭제
**Request**: `DELETE /trashcans/{trashcan_id}`

**Response 예시**
```json
{ "deleted": true, "soft_deleted": true }
```
**Response (이미 삭제됨)**
```json
{ "deleted": true, "already_deleted": true }
```

**Response (실패 예시)**
```json
{ "deleted": false, "reason": "not_found" }
```

## 5-0) 쓰레기통 복구
**Request**: `POST /trashcans/{trashcan_id}/restore`

**Response 예시**
```json
{ "restored": true }
```

## 5-1) 쓰레기통 요약 (종류별 통계/여유공간)
**Request**: `GET /trashcans/{trashcan_id}/summary`

**Query**
- `window_days` (기본 7)
- `full_threshold` (기본 50)
- `medium_threshold` (기본 20)

**Response 예시**
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

## 5-2) 쓰레기통 연결 테스트
**Request**: `POST /trashcans/{trashcan_id}/connection-test`

**설명**
- 현재 `is_online` 상태를 기준으로 결과 반환
- 온라인이면 `last_connected_at`을 테스트 시각으로 갱신

**Response 예시**
```json
{
  "trashcan_id": 3,
  "is_online": true,
  "last_connected_at": null,
  "tested_at": "2026-01-26T09:00:00",
  "result": "online"
}
```

## 6) 쓰레기 종류 등록
**Request**: `POST /waste-types`

**Body 예시**
```json
{ "type_name": "Plastic" }
```

**Response 예시**
```json
{ "waste_type_id": 1, "type_name": "Plastic" }
```

## 7) 쓰레기 종류 삭제
**Request**: `DELETE /waste-types/{waste_type_id}`

**Response 예시**
```json
{ "deleted": true }
```

**Response (실패 예시)**
```json
{ "deleted": false, "reason": "in_use" }
```

## 8) 쓰레기 종류 시드 등록
**Request**: `POST /waste-types/seed?types=Plastic&types=PET%20Bottle&types=Can&types=Styrofoam`

**Response 예시**
```json
{ "created": 4, "skipped": 0 }
```

## 9) 대시보드 요약 (전체)
**Request**: `GET /dashboard/summary`

**Response 예시**
```json
{
  "total_objects": 2,
  "total_events": 1,
  "by_type": { "Plastic": 1, "PET Bottle": 1 }
}
```

## 10) 대시보드 요약 (쓰레기통별)
**Request**: `GET /dashboard/summary/trashcans`

**Response 예시**
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

## 11) 기간 통계
**Request**
- `GET /dashboard/stats?period=week|month|year`
- 또는 `GET /dashboard/stats?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

**Response 예시**
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

## 12) 수거 필요 쓰레기통 조회
**Request**: `GET /trashcans/collection-needed`

**Query**
- `window_days` (기본 7)
- `full_threshold` (기본 50)
- `medium_threshold` (기본 20)
- `status`: `full|medium|low|unknown`
- `sort`: `status|count`

**Response 예시**
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

## 13) 미연결 쓰레기통 조회
**Request**: `GET /trashcans/offline?stale_hours=24`

**Response 예시**
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
