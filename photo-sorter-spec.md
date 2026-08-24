# 사진 자동 리사이즈 + 품질 분류 프로그램 명세서

## 목적
지정 폴더에 사진을 넣으면 자동으로:
1. 긴 축 기준 3840px로 리사이즈
2. 초점 안 맞는(흐린) 사진 판별
3. 눈 감은 사진 판별
4. 판별 결과에 따라 하위 폴더로 분류 (삭제하지 않음)

## 기술 스택
- Python 3.10+
- watchdog — 폴더 감시
- Pillow — 리사이즈, EXIF 처리
- OpenCV — Laplacian variance 기반 블러 판별
- MediaPipe Face Mesh — 얼굴 랜드마크 추출, EAR 기반 눈 감김 판별

## 동작 흐름
```
watch_folder/  (감시 대상, 사용자가 사진을 넣는 곳)
├── ok/            # 정상 사진 (리사이즈 완료본)
├── blur/          # 흐림 의심
├── eyes_closed/   # 눈 감음 의심
└── originals/     # 원본 백업 (선택)
```

1. watchdog으로 watch_folder에 새 이미지 파일(jpg/jpeg/png/heic) 생성 이벤트 감지
2. **파일 복사 완료 대기**: 파일 크기가 1초 간격 2회 연속 동일할 때까지 대기 후 처리 시작
3. EXIF 회전 정보 적용 (`ImageOps.exif_transpose`)
4. 긴 축이 3840px 초과 시 비율 유지 리사이즈 (LANCZOS 필터), JPEG quality=90
5. 블러 판별 → 눈 감김 판별 순서로 검사
6. 결과에 따라 해당 하위 폴더로 이동. 원본은 originals/에 보관

## 판별 로직 상세

### 블러 판별
- 그레이스케일 변환 후 `cv2.Laplacian(img, cv2.CV_64F).var()` 계산
- MediaPipe로 얼굴이 검출되면 **얼굴 영역만 크롭해서** 선명도 측정 (배경 아웃포커싱 인물 사진 오판 방지)
- 얼굴이 없으면 이미지 중앙 60% 영역으로 측정
- 임계값은 config로 분리 (기본값 100, 사용자가 튜닝 가능)

### 눈 감김 판별
- MediaPipe Face Mesh로 눈 랜드마크 추출
- EAR(Eye Aspect Ratio) = 눈 세로 거리 / 가로 거리 계산
- 양쪽 눈 EAR 평균이 임계값(기본 0.18, config 분리) 이하면 감은 것으로 판정
- **여러 명 검출 시**: 한 명이라도 감으면 eyes_closed로 분류
- 얼굴 미검출 시 눈 감김 검사는 건너뜀 (블러 결과만 적용)
- 웃어서 눈이 가늘어진 경우 오판 가능하므로 임계값은 보수적으로(낮게) 시작

## 설정 파일 (config.yaml 또는 config.json)
```yaml
watch_folder: "C:/Users/<사용자명>/Desktop/Photos"   # 바탕화면의 Photos 폴더
max_long_edge: 3840
jpeg_quality: 90
blur_threshold: 100
ear_threshold: 0.18
keep_originals: true
strip_gps_exif: true    # 블로그 업로드용이므로 위치정보 제거
```

## 요구사항
- 프로그램 시작 시 폴더에 이미 있는 미처리 파일도 일괄 처리
- 처리 결과를 콘솔 + 로그 파일에 기록 (파일명, 판정, 측정값)
- 동일 파일명 충돌 시 `_1`, `_2` 접미사로 저장
- 판별 측정값(Laplacian variance, EAR)을 로그에 남겨서 임계값 튜닝에 활용할 수 있게
- 오탐이 있을 수 있으므로 **어떤 경우에도 파일을 삭제하지 않는다**
- Windows 기준 실행 (경로 처리 pathlib 사용)
- 감시 폴더는 바탕화면의 `Photos` 폴더로 확정. 프로그램 시작 시 폴더가 없으면 자동 생성
- 바탕화면 경로는 하드코딩하지 말고 실행 시 실제 경로를 확인할 것 (OneDrive 사용 PC는 바탕화면이 `C:/Users/<사용자명>/OneDrive/바탕 화면`으로 리다이렉트되어 있을 수 있음)

## 개발 순서 제안
1. 리사이즈 + 폴더 감시만 먼저 (핵심 파이프라인)
2. 블러 판별 추가
3. 눈 감김 판별 추가
4. 샘플 사진 20~30장으로 임계값 튜닝

## 주의사항 (Claude Code에게)
- 과도한 추상화 없이 단일 스크립트 + config 구조로 시작
- MediaPipe는 `pip install mediapipe`로 설치, Python 버전 호환성 먼저 확인
- HEIC 지원이 필요하면 `pillow-heif` 추가
