## 전체 API 테스트 가이드 (PowerShell)

아래 순서는 **실제 운영 흐름대로** 모든 엔드포인트를 테스트할 수 있도록 구성했습니다.

### 0) 서버 실행
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

### 1) 헬스체크
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health"
```

### 2) 쓰레기 종류 등록/삭제
#### 2-1) Seed 등록
```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/waste-types/seed?types=Plastic&types=Glass%20Bottle&types=Can&types=Styrofoam"
```

#### 2-2) 개별 등록 후 삭제 (삭제 테스트용)
```powershell
$wt = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/waste-types" -ContentType "application/json" -Body '{"type_name":"TempType"}'
Invoke-RestMethod -Method Delete "http://127.0.0.1:8000/waste-types/$($wt.waste_type_id)"
```

### 3) 쓰레기통 생성/조회/수정/삭제/복구
#### 3-1) 쓰레기통 여러 개 생성
```powershell
$trashcanA = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/trashcans" -ContentType "application/json" -Body '{
  "trashcan_name": "TrashCan A",
  "trashcan_capacity": 100,
  "trashcan_city": "Seoul",
  "address_detail": "Test Road 1",
  "trashcan_latitude": 37.5665,
  "trashcan_longitude": 126.9780,
  "is_online": true
}'
$trashcanB = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/trashcans" -ContentType "application/json" -Body '{
  "trashcan_name": "TrashCan B",
  "trashcan_capacity": 60,
  "trashcan_city": "Busan",
  "address_detail": "Test Road 2",
  "trashcan_latitude": 35.1796,
  "trashcan_longitude": 129.0756,
  "is_online": false
}'
$trashcanC = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/trashcans" -ContentType "application/json" -Body '{
  "trashcan_name": "TrashCan C",
  "trashcan_capacity": 80,
  "trashcan_city": "Incheon",
  "address_detail": "Test Road 3",
  "trashcan_latitude": 37.4563,
  "trashcan_longitude": 126.7052,
  "is_online": true
}'
$trashcanAId = $trashcanA.trashcan_id
$trashcanBId = $trashcanB.trashcan_id
$trashcanCId = $trashcanC.trashcan_id
```

#### 3-2) 쓰레기통 목록/위치 조회
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans?offset=0&limit=50&sort=total_desc"
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/locations?offset=0&limit=50"
```

#### 3-3) 쓰레기통 수정 (PATCH/POST)
```powershell
Invoke-RestMethod -Method Patch "http://127.0.0.1:8000/trashcans/$trashcanAId" -ContentType "application/json" -Body '{
  "trashcan_name": "TrashCan A-Updated",
  "trashcan_capacity": 120,
  "trashcan_city": "Seoul",
  "is_online": true
}'
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/trashcans/$trashcanBId" -ContentType "application/json" -Body '{
  "address_detail": "Updated Road 2",
  "trashcan_latitude": 35.1796,
  "trashcan_longitude": 129.0756
}'
```

#### 3-4) 쓰레기통 요약/연결 테스트
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/$trashcanAId/summary?window_days=7&full_threshold=50&medium_threshold=20"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/trashcans/$trashcanAId/connection-test"
```

#### 3-5) 쓰레기통 삭제/복구
```powershell
Invoke-RestMethod -Method Delete "http://127.0.0.1:8000/trashcans/$trashcanCId"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/trashcans/$trashcanCId/restore"
```

### 4) 탐지 데이터 저장 (쓰레기통별로 다르게)
#### 4-1) TrashCan A 탐지 저장
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/detections" -Method Post -ContentType "application/json" -Body '{
  "trashcan_id": '"$trashcanAId"',
  "filename": "tc-a-1.jpg",
  "saved_path": "detect_img/tc-a-1.jpg",
  "object_count": 2,
  "objects": [
    { "class_id": 2, "class_name": "Plastic", "confidence": 0.91, "box": { "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0 } },
    { "class_id": 3, "class_name": "Can", "confidence": 0.88, "box": { "x1": 50.0, "y1": 60.0, "x2": 80.0, "y2": 100.0 } }
  ]
}'
```

#### 4-2) TrashCan B 탐지 저장
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/detections" -Method Post -ContentType "application/json" -Body '{
  "trashcan_id": '"$trashcanBId"',
  "filename": "tc-b-1.jpg",
  "saved_path": "detect_img/tc-b-1.jpg",
  "object_count": 1,
  "objects": [
    { "class_id": 1, "class_name": "PET Bottle", "confidence": 0.93, "box": { "x1": 12.0, "y1": 24.0, "x2": 36.0, "y2": 48.0 } }
  ]
}'
```

#### 4-3) valid-2.json 샘플 저장 (옵션)
```powershell
$file = "C:\Users\bhs20\OneDrive\바탕 화면\YOLO 데이터\valid-2.json"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/detections" -Method Post -ContentType "application/json" -InFile $file
```

### 5) 탐지 상세/상태 조회
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/detections/details?waste_type=전체&offset=0&limit=20"
Invoke-RestMethod "http://127.0.0.1:8000/detections/details?waste_type=can&offset=0&limit=20"
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/$trashcanAId/summary?window_days=7&full_threshold=50&medium_threshold=20"
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/collection-needed?window_days=7&full_threshold=50&medium_threshold=20&sort=status"
Invoke-RestMethod "http://127.0.0.1:8000/trashcans/offline?stale_hours=24"
```

### 6) 대시보드 요약/통계
```powershell
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/summary"
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/summary/trashcans"
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/stats?period=week"
Invoke-RestMethod "http://127.0.0.1:8000/dashboard/stats?start_date=2026-01-20&end_date=2026-01-29"
```

### 7) 일별 통계 삭제/재생성
```powershell
Invoke-RestMethod -Method Delete "http://127.0.0.1:8000/daily-stats?start_date=2026-01-01&end_date=2026-01-07"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/daily-stats/rebuild?start_date=2026-01-01&end_date=2026-01-07"
```

### 8) 탐지 데이터 삭제
```powershell
Invoke-RestMethod -Method Delete "http://127.0.0.1:8000/detections?start_date=2026-01-29&end_date=2026-01-29"
Invoke-RestMethod -Method Delete "http://127.0.0.1:8000/detections/recent?days=7"
```
