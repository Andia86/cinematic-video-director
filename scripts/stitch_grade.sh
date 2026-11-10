#!/usr/bin/env bash
# 拼接多段 10 秒视频。默认统一调成电影色调（青橙调 + 轻微暗角）；
# 带 --raw 时只拼接重编码，不动颜色，用于用户要求保留原始质感的片子。
# 用法: stitch_grade.sh [--raw] <输出文件> <片段1> <片段2> [更多片段...]
# 依赖: ffmpeg / ffprobe（本机可用）。
set -euo pipefail

RAW=0
if [ "${1:-}" = "--raw" ]; then RAW=1; shift; fi

OUT="${1:?用法: stitch_grade.sh [--raw] <输出文件> <片段1> <片段2> [...]}"
shift
[ "$#" -ge 1 ] || { echo "至少需要一个片段" >&2; exit 1; }

TMPDIR_WORK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_WORK"' EXIT

LIST="$TMPDIR_WORK/list.txt"
: > "$LIST"
for f in "$@"; do
  [ -f "$f" ] || { echo "片段不存在: $f" >&2; exit 1; }
  # concat 列表用单引号包裹路径，路径本身含单引号时必须转义，否则 ffmpeg 解析失败
  esc="$(readlink -f "$f" | sed "s/'/'\\\\''/g")"
  printf "file '%s'\n" "$esc" >> "$LIST"
done

if [ "$RAW" -eq 1 ]; then
  ffmpeg -y -v error -f concat -safe 0 -i "$LIST" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -movflags +faststart "$OUT"
else
  # 电影色调：对比与饱和微升，阴影偏青、高光偏暖，加轻微暗角。
  GRADE="eq=contrast=1.08:saturation=1.12:brightness=0.01,colorbalance=rs=0.03:gs=0.05:bs=0.14:rm=0.00:gm=0.01:bm=0.00:rh=0.10:gh=0.03:bh=-0.08,vignette=angle=PI/5"
  ffmpeg -y -v error -f concat -safe 0 -i "$LIST" \
    -vf "$GRADE" -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -movflags +faststart "$OUT"
fi

DUR="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")"
echo "完成: $OUT （总时长 ${DUR} 秒）"
