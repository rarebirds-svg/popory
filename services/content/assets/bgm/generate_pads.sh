#!/bin/bash
# 영상 BGM용 저작권-안전 앰비언트 패드를 ffmpeg 합성으로 생성하는 스크립트(다양한 키·분위기).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
FFMPEG="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"
FFPROBE="${FFPROBE_BIN:-/opt/homebrew/bin/ffprobe}"
DUR=62           # 합성 길이(초). 끝 페이드 여유 포함, 최종 60초로 트림.
TARGET_LUFS=-31.5 # 기존 pad_*.mp3 의 지각 음량(integrated LUFS)에 맞춤. mean(RMS)이 아니라
                  # LUFS 로 맞춰야 크레스트가 다른 곡끼리도 체감 BGM 레벨이 일관된다.

# 각 항목 = "파일명 근음 3화음주파수들(공백구분) lowpass컷(Hz)".
# 근음을 낮게(옥타브 베이스) + 3화음으로 따뜻한 패드. lowpass 로 음색 밝기 조절.
PADS=(
  "pad_hope_g        98.00  98.00 123.47 146.83 196.00   1100"  # G major, 희망적
  "pad_deep_emin     82.41  82.41 98.00  123.47 164.81    900"  # E minor, 깊고 사색적
  "pad_bright_f     174.61 174.61 220.00 261.63 349.23   1500"  # F major, 밝음
  "pad_soft_dmin    146.83 146.83 174.61 220.00 293.66   1000"  # D minor, 부드러움
  "pad_warm_c       130.81 130.81 164.81 196.00 261.63   1150"  # C major, 따뜻함
  "pad_still_amin   110.00 110.00 130.81 164.81 220.00    850"  # A minor, 고요함
)

lufs_of () { # $1=file → integrated LUFS
  "$FFMPEG" -hide_banner -nostats -i "$1" -af ebur128=framelog=quiet -f null /dev/null 2>&1 \
    | awk '/Integrated loudness:/{f=1} f&&/I:/{print $2; f=0}'
}

for row in "${PADS[@]}"; do
  read -r name _root f1 f2 f3 f4 lp <<< "$row"
  raw="$DIR/.${name}.raw.wav"
  out="$DIR/${name}.mp3"
  # 4성부 사인 + 미세 디튠(f1+0.4Hz)으로 두께 → amix → 느린 트레몰로(움직임) → lowpass(음색)
  # → aecho(공간감) → 페이드 → mono/48k. tremolo 로 정적인 패드에 숨결을 준다.
  "$FFMPEG" -y -hide_banner -loglevel error \
    -f lavfi -i "sine=frequency=$f1:duration=$DUR" \
    -f lavfi -i "sine=frequency=$f2:duration=$DUR" \
    -f lavfi -i "sine=frequency=$f3:duration=$DUR" \
    -f lavfi -i "sine=frequency=$f4:duration=$DUR" \
    -f lavfi -i "sine=frequency=$(echo "$f1+0.4" | bc):duration=$DUR" \
    -filter_complex \
    "[0][1][2][3][4]amix=inputs=5:normalize=1,tremolo=f=0.1:d=0.15,lowpass=f=$lp,aecho=0.8:0.7:70:0.35,afade=t=in:st=0:d=4,afade=t=out:st=56:d=4" \
    -ac 1 -ar 48000 -t 60 "$raw"
  # 기존 곡과 음량 매칭: LUFS 측정 → TARGET_LUFS 까지 볼륨 보정(LUFS 는 dB 선형) → mp3 저장
  l=$(lufs_of "$raw")
  gain=$(echo "$TARGET_LUFS - ($l)" | bc)
  "$FFMPEG" -y -hide_banner -loglevel error -i "$raw" -af "volume=${gain}dB" -ac 1 -ar 48000 -codec:a libmp3lame -q:a 4 "$out"
  rm -f "$raw"
  echo "$(basename "$out"): $(lufs_of "$out") LUFS (target ${TARGET_LUFS})"
done

echo "완료. assets/bgm/ 의 *.mp3 개수: $(ls "$DIR"/*.mp3 | wc -l | tr -d ' ')"
