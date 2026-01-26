# Trash Detection API 문서

YOLO 객체 탐지 결과(`valid-2.json`)를 MySQL에 저장하기 위한 최소 FastAPI 백엔드입니다.

## 1) 구성 요약
- `database.py`: DB 연결/세션/베이스 설정
- `model.py`: 정규화 테이블 모델 (`detections`, `detection_objects`)
- `main.py`: FastAPI 앱 + `/detections` 저장 API

## 2) 설치
```bash
pip install fastapi uvicorn sqlalchemy pymysql pydantic
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
  "source_image": "809439@0_05001_220907_P1_T3__0281.jpg",
  "total_objects": 1,
  "predictions": [
    {
      "class_id": 3,
      "class_name": "Styrofoam",
      "confidence": 0.8481,
      "box": { "x1": 1042.8, "y1": 170.3, "x2": 1376.2, "y2": 626.7 }
    }
  ]
}
```

응답 예시:
```json
{ "detection_id": 1, "total_objects": 1 }
```

## 6) 테이블 구조

### detections
- 이미지 단위 탐지 이벤트
- 주요 컬럼: `source_image`, `total_objects`, `detected_at`

### detection_objects
- 개별 객체 탐지 결과
- 주요 컬럼: `class_id`, `class_name`, `confidence`, `x1~y2`

## 7) 참고
- 자동 문서화: `http://localhost:8000/docs`
