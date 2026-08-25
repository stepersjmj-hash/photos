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

## 자동 시작 (이 PC에 설정됨)
- 시작 프로그램 바로가기: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Photo Sorter.lnk`
  → `pythonw.exe photo_sorter.py` (콘솔 창 없이 백그라운드 실행)
- 로그인하면 자동 실행됨. 해제하려면 위 .lnk 삭제. 즉시 종료는 작업관리자에서 pythonw 종료
- Windows named mutex 로 중복 실행 방지 — 수동으로 또 실행하면 바로 종료됨
- **주의: 코드를 수정하면 python.exe/pythonw.exe 전부 확인 후 재시작할 것.**
  구버전 코드가 메모리에 남은 프로세스가 살아 있으면 (특히 mutex 도입 전 버전)
  두 인스턴스가 같은 파일을 경쟁 처리해 중복본·오분류가 대량 발생함 (2026-08-25 사고).
  확인: `Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'"`
- pythonw 는 stdout 이 없으므로 setup_logging/print 에 `sys.stdout is not None` 가드 필요 (적용됨)

## 판별 로직 요약
- 얼굴 검출 3단계 체인: FaceMesh(1280px) → Haar(1600px, minNeighbors=4) →
  ±90도 회전 후 재시도. 찾은 얼굴은 크롭을 512px 이상으로 확대해
  refine_landmarks=True 로 정밀 재측정 (EAR·선명도 모두 여기서).
- 블러: 얼굴 있으면 얼굴 크롭 선명도 최댓값 vs `blur_threshold_face`(8),
  없으면 중앙 60% vs `blur_threshold_center`(120). 측정 패치는 긴 축 512px 정규화.
  얼굴 크롭은 피부 위주라 선명해도 값이 낮음 — 두 모드 임계값 절대 통합 금지.
- 눈 감김: 표준 6점 EAR(세로 2쌍 평균/가로). `ear_threshold`(0.17) 이하 한 명이라도
  있으면 eyes_closed. 얼굴 미검출 시 건너뜀.
- 판정 우선순위: blur → eyes_closed → ok
- 로그(`<watch_folder>/photo_sorter.log`)에 blur값[모드]·검출단계·EAR 기록됨
- 2026-08-25 실사진 34장 튜닝 결과: 31/34, 오탐(선명→blur) 0.
  실측 분포 — 감은 눈 EAR 0.135~0.153 / 뜬 눈 0.201~0.494,
  선명 얼굴 blur 12.9~85.6 / 중앙측정 선명 209~708, 흐림 9.6~33.3

## 함정 및 해결책
- **MediaPipe 1.x 는 레거시 `mp.solutions.face_mesh` API가 제거됨** —
  반드시 `mediapipe==0.10.21` 사용 (requirements.txt 에 고정됨). Python 3.10 호환.
- 바탕화면 경로는 OneDrive 리다이렉트 가능성 때문에 하드코딩 금지 —
  `SHGetFolderPathW` 로 실행 시 감지 (`get_desktop_path()`)
- Laplacian variance 는 이미지 크기에 따라 값이 달라지므로 측정 패치를
  긴 축 512px로 정규화해서 임계값 일관성 유지
- HEIC 는 `pillow-heif` 로 읽고 출력은 JPEG 로 변환
- EXIF 촬영정보(촬영일시·노출·렌즈·MakerNote 등)는 결과물에 그대로 보존됨
  (`exif.tobytes()` 가 Exif 하위 IFD까지 직렬화). GPS 도 유지가 기본값
  (`strip_gps_exif: true` 로 바꾸면 위치정보만 제거).
  ICC 색상 프로파일도 `save(icc_profile=...)` 로 보존 — 빼먹으면 Adobe RGB 사진 색이 틀어짐
- `keep_originals: false` 여도 삭제 금지 원칙상 원본은 originals/ 에 보관됨
- **FaceMesh 기본 검출은 아이 사진(작은 얼굴·전신 샷·누운 얼굴·꼭 감고 웃는 눈)을
  절반 가까이 놓침** — Haar 폴백과 회전 재시도가 필수. Haar 오탐은 크롭에서
  mesh 재검출 실패로 걸러짐. 작은 얼굴 EAR 은 크롭 확대 없이 재면
  '뜬 눈' 쪽으로 뭉개져서 감김 판별이 안 됨.

## 알려진 한계 (2026-08-25 튜닝 기준)
- 내리깐 눈(장난감 보는 아이 등)과 옆으로 누운 얼굴은 랜드마크가 '뜬 눈'으로
  읽어 eyes_closed 를 놓칠 수 있음 (ok 로 감 — 안전한 방향)
- 유리 너머 촬영(반사 겹침)은 창틀 등 선명한 에지 때문에 중앙측정 blur 를 놓침
- 선글라스 낀 얼굴은 EAR 무의미 (실측에서는 오탐 없었음)
