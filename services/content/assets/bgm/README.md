# 영상 BGM (무료·저작권 안전 음원만)

이 폴더의 `*.mp3`가 생성 영상에 배경음악으로 깔립니다(`video.py _master_audio` — BGM volume 2.5 + amix normalize=0 + loudnorm, 말소리보다 ~3dB 아래의 배경 베드). 파일이 없으면 BGM 없이 음량정규화만 됩니다. 작업마다 `_pick_bgm`이 job_id로 하나를 결정적으로 고릅니다(파일 추가 시 워커 재시작 불필요 — 매번 glob).

## 현재 음원 (합성 앰비언트 패드 9곡)

전부 `generate_pads.sh`로 ffmpeg 합성한 저작권-무관 패드입니다(다운로드 음원 아님). 여러 키·분위기로 다양성 확보. 전 곡 **-31.5 LUFS**로 지각 음량을 맞춰, 어떤 곡이 뽑혀도 BGM 크기가 일관됩니다.

- 기존 3곡. `pad_calm_c` `pad_bright_d` `pad_warm_am`
- 추가 6곡. `pad_hope_g`(희망) `pad_deep_emin`(사색) `pad_bright_f`(밝음) `pad_soft_dmin`(부드러움) `pad_warm_c`(따뜻) `pad_still_amin`(고요)

## 곡 추가 방법

### A. 합성으로 추가 (권장 · 저작권 100% 안전)
`generate_pads.sh` 의 `PADS` 배열에 `"파일명 근음 주파수들 lowpass컷"` 한 줄 추가 후 실행.
```
bash generate_pads.sh
```
LUFS 자동 매칭이라 음량 걱정 없이 늘어납니다.

### B. 무료 음원 다운로드로 추가
`*.mp3`를 이 폴더에 넣으면 자동 포함됩니다. **단, 다운로드 음원은 합성곡보다 대개 크므로 다른 곡과 음량이 어긋날 수 있습니다.** 아래 명령으로 -31.5 LUFS에 맞춰 넣으세요.
```
ffmpeg -i 원본.mp3 -af "loudnorm=I=-31.5:TP=-3" -ac 1 -ar 48000 새이름.mp3
```
음원 출처(무료·저작권 안전).
- YouTube 오디오 보관함 (studio.youtube.com → 오디오 보관함). 수익화·저작권 안전.
- Pixabay Music (pixabay.com/music) — CC0.
- incompetech.com (Kevin MacLeod) — CC-BY, 영상 설명란에 출처 표기 필요.

## 주의
- 저작권 불명 음원 금지. 반드시 CC0 또는 사용 허가된 음원만.
- CC-BY(예: incompetech) 음원을 쓰면 영상 설명란에 출처 표기를 반드시 넣는다.
- 파일명 자유. 여러 개 두면 작업마다 결정적으로 하나가 선택됩니다.
