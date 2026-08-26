# Photo Sorter — 사진 자동 리사이즈 + 품질 분류

바탕화면의 **`Photos` 폴더에 사진을 넣기만 하면** 자동으로 긴 축 3840px로 리사이즈하고,
흐린 사진 / 눈 감은 사진을 골라내 하위 폴더로 옮겨 줍니다.
**어떤 경우에도 파일을 삭제하지 않습니다** — 원본은 `originals/` 에 그대로 보관됩니다.

- 저장소: https://github.com/stepersjmj-hash/photos
- 실행 환경: Windows + Python 3.10 이상 (macOS/Linux 도 감시 폴더를 직접 지정하면 동작)

## 설치

```bash
pip install -r requirements.txt
```

MediaPipe 는 `0.10.21` 버전이 고정되어 있습니다 (1.x 는 얼굴 인식 API가 제거됨). Python 3.10 권장.

## 실행

```bash
python photo_sorter.py
```

실행하면 바탕화면 경로를 자동으로 찾아 `<바탕화면>\Photos` 폴더와 하위 폴더를 만들고,
이미 들어 있던 사진을 먼저 처리한 뒤 계속 감시합니다. 종료는 `Ctrl+C`.

| 명령 | 하는 일 |
| --- | --- |
| `python photo_sorter.py` | 기존 파일 처리 후 계속 감시 (기본) |
| `python photo_sorter.py --once` | 지금 폴더에 있는 파일만 처리하고 종료 |
| `python photo_sorter.py --config 다른설정.yaml` | 다른 설정 파일로 실행 |

## 사용법 — 사진 넣기

바탕화면 `Photos` 폴더에 사진을 복사(또는 이동)하면 끝입니다. 몇 초 뒤 자동으로 분류됩니다.

```
바탕화면\Photos\
├── ok/            정상 사진 (리사이즈 완료본)
├── blur/          흐림 의심
├── eyes_closed/   눈 감음 의심
├── originals/     원본 보관 (리사이즈 전 파일)
└── photo_sorter.log   처리 기록
```

- 지원 형식: **JPG · JPEG · PNG · HEIC** (HEIC 는 JPEG 로 변환되어 저장)
- 파일 복사가 끝날 때까지 기다렸다가 처리하므로, 큰 파일을 넣어도 안전합니다
- 같은 이름이 있으면 `_1`, `_2` 를 붙여 저장합니다
- 촬영일시·노출·렌즈 같은 **EXIF 정보와 색상 프로파일(ICC)은 그대로 보존**됩니다.
  GPS 위치정보도 기본으로 유지 — 빼고 싶으면 아래 설정에서 `strip_gps_exif: true`
- 결과가 마음에 안 들면 `blur/` `eyes_closed/` 안의 사진을 직접 `ok/` 로 옮기면 됩니다.
  (분류는 어디까지나 "의심" 표시이고, 지워지는 파일은 없습니다)

## 로그인할 때 자동 실행하기

1. `Win+R` → `shell:startup` 입력해 시작 프로그램 폴더를 엽니다
2. 그 안에 바로가기를 하나 만들고, 대상에 아래처럼 넣습니다 (경로는 본인 환경에 맞게)

```
pythonw.exe "C:\Users\<사용자명>\Desktop\mj\photos\photo_sorter.py"
```

`python.exe` 가 아니라 **`pythonw.exe`** 를 쓰면 검은 콘솔 창 없이 백그라운드로 돕니다.
- 중지: 바로가기를 지우고, 작업관리자에서 `pythonw.exe` 종료
- 이미 돌고 있을 때 또 실행해도 중복 실행되지 않고 바로 종료됩니다 (안전장치 내장)
- 콘솔이 없으므로 진행 상황은 `Photos\photo_sorter.log` 에서 확인하세요

## 설정 바꾸기 (`config.yaml`)

코드를 고치지 않고 `config.yaml` 만 수정하면 됩니다. 수정 후에는 프로그램을 재시작하세요.

| 항목 | 기본값 | 설명 |
| --- | --- | --- |
| `watch_folder` | `null` | 감시할 폴더. `null` 이면 `<바탕화면>\Photos` 자동 사용 |
| `max_long_edge` | `3840` | 리사이즈할 긴 축 픽셀 (이보다 작은 사진은 그대로) |
| `jpeg_quality` | `90` | JPEG 저장 품질 |
| `blur_threshold_face` | `8` | 얼굴이 검출된 사진의 흐림 기준 |
| `blur_threshold_person` | `30` | 인물 영역 흐림 보조 기준 (배경만 선명한 사진 잡기) |
| `blur_threshold_center` | `120` | 얼굴·인물 모두 없을 때 중앙부 흐림 기준 |
| `ear_threshold` | `0.17` | 눈 감김 기준 (높일수록 더 많이 "감았다"고 판정) |
| `strip_gps_exif` | `false` | `true` 로 하면 사진에서 GPS 위치정보 제거 |

**흐린 사진을 자꾸 놓친다면** 해당 `blur_threshold_*` 를 조금 올리고,
**멀쩡한 사진이 blur 로 간다면** 내리세요. 값은 로그의 `blur=...[모드]` 기록을 보고 조정하면 됩니다.
세 임계값은 측정 방식이 서로 달라 값의 스케일이 다릅니다 — 하나로 통일하지 마세요.

## 잘 안 될 때

- **아무 일도 안 일어남** → `Photos\photo_sorter.log` 를 열어 보세요. 감시 폴더 경로가 첫 줄에 찍힙니다
- **HEIC 가 처리되지 않음** → 로그 첫 줄의 `HEIC 지원: False` 확인 후 `pip install pillow-heif`
- **설치 중 MediaPipe 오류** → Python 3.10 인지 확인 (3.12 이상에서는 0.10.21 설치가 안 될 수 있음)
- **눈 감았는데 ok 로 감** → 고개를 푹 숙였거나 완전 옆모습이면 눈을 찾지 못합니다 (알려진 한계)

더 자세한 판별 로직과 튜닝 근거는 [CLAUDE.md](CLAUDE.md), 최초 설계는 [photo-sorter-spec.md](photo-sorter-spec.md) 참고.
