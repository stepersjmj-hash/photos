# photos — 사진 자동 리사이즈 + 품질 분류

바탕화면 `Photos` 폴더를 감시해 새 사진을 자동으로 리사이즈(긴 축 3840px)하고
블러/눈 감김을 판별해 `ok/` `blur/` `eyes_closed/` 하위 폴더로 분류하는 프로그램.
원본은 `originals/` 에 보관하며 어떤 경우에도 파일을 삭제하지 않는다.

## 파일 구성
- `photo_sorter.py` — 단일 스크립트 (감시 + 리사이즈 + 판별 + 분류)
- `config.yaml` — 임계값·경로 설정. `watch_folder: null` 이면 실행 시 실제 바탕화면 경로 자동 감지
- `photo-sorter-spec.md` — 원본 명세서
- `requirements.txt` — 의존성

## 실행 방법
```
pip install -r requirements.txt
python photo_sorter.py            # 기존 파일 일괄 처리 후 감시 시작
python photo_sorter.py --once     # 기존 파일만 처리하고 종료 (테스트용)
python photo_sorter.py --config <경로>   # 다른 config 사용
```

## 판별 로직 요약
- 블러: 얼굴 영역(없으면 중앙 60%)을 긴 축 512px로 정규화 후 Laplacian variance.
  `blur_threshold`(기본 100) 이하이면 blur 판정. 여러 얼굴이면 최댓값 사용.
- 눈 감김: MediaPipe Face Mesh EAR(세로/가로). 양쪽 눈 평균이 `ear_threshold`(기본 0.18)
  이하인 얼굴이 한 명이라도 있으면 eyes_closed. 얼굴 미검출 시 건너뜀.
- 판정 우선순위: blur → eyes_closed → ok
- 로그(`<watch_folder>/photo_sorter.log`)에 blur값·EAR값이 남으므로 이를 보고 임계값 튜닝

## 함정 및 해결책
- **MediaPipe 1.x 는 레거시 `mp.solutions.face_mesh` API가 제거됨** —
  반드시 `mediapipe==0.10.21` 사용 (requirements.txt 에 고정됨). Python 3.10 호환.
- 바탕화면 경로는 OneDrive 리다이렉트 가능성 때문에 하드코딩 금지 —
  `SHGetFolderPathW` 로 실행 시 감지 (`get_desktop_path()`)
- Laplacian variance 는 이미지 크기에 따라 값이 달라지므로 측정 패치를
  긴 축 512px로 정규화해서 임계값 일관성 유지
- HEIC 는 `pillow-heif` 로 읽고 출력은 JPEG 로 변환
- EXIF 촬영정보(촬영일시·노출·렌즈·MakerNote 등)는 결과물에 그대로 보존됨
  (`exif.tobytes()` 가 Exif 하위 IFD까지 직렬화). GPS만 설정에 따라 제거.
  ICC 색상 프로파일도 `save(icc_profile=...)` 로 보존 — 빼먹으면 Adobe RGB 사진 색이 틀어짐
- `keep_originals: false` 여도 삭제 금지 원칙상 원본은 originals/ 에 보관됨

## 남은 작업
- 샘플 사진 20~30장으로 blur_threshold / ear_threshold 튜닝 (개발 순서 4단계)
