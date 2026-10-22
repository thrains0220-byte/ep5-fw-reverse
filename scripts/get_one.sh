#!/usr/bin/env bash
# 单目标、耐心重试的 Wayback 固件下载
# 用法: get_one.sh <model4> <ver4> [max_retry]
cd /home/sanyu/Projects/work/ep5-af-fix
unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy ALL_PROXY all_proxy
M="$1"; V="$2"; MAX=${3:-40}
MS="${M%0}"
FN="OLY_E_${MS}_${V}_0000_0000.BIN"
DST="/home/sanyu/Projects/work/ep5-af-fix/fw2/${FN}"
PARTS="/tmp/wbpart_${M}_${V}"
mkdir -p "$PARTS"
BASE="https://dl01.om-digitalsolutions.net/OMDS/FIRMWARES/0001/${M}/${FN}"
LEN=""
for ts in 20250201203957 20240628205426 20240213194626 20230912191251 20210101000000; do
  URL="https://web.archive.org/web/${ts}id_/${BASE}"
  for try in 1 2 3 4 5 6; do
    HDRS=$(curl -4 -s -o /dev/null -D - --max-time 90 -r 0-0 "$URL" 2>/dev/null | tr -d '\r')
    LEN=$(printf '%s\n' "$HDRS" | awk 'tolower($1)=="x-archive-orig-content-length:"{print $2}' | tail -1)
    [ -z "${LEN:-}" ] && LEN=$(printf '%s\n' "$HDRS" | awk 'tolower($1)=="content-range:"{split($2,a,"/"); print a[2]}' | tail -1)
    if [ -n "${LEN:-}" ] && [ "$LEN" -gt 1000000 ]; then break 2; fi
    LEN=""
    sleep $((try*5))
  done
done
if [ -z "${LEN:-}" ]; then echo "  [$FN] 长度探测失败"; exit 1; fi
echo "  [$FN] 总长 $LEN 字节"
CHUNK=$((1024*1024)); N=$(( (LEN + CHUNK - 1) / CHUNK ))
: > "$PARTS/jobs.txt"
for i in $(seq 0 $((N-1))); do
  s=$((i*CHUNK)); e=$((s+CHUNK-1)); [ $e -ge $LEN ] && e=$((LEN-1))
  printf '%04d %d %d\n' "$i" "$s" "$e" >> "$PARTS/jobs.txt"
done
worker() {
  while read -r idx s e; do
    out="$PARTS/p$idx"; want=$((e - s + 1))
    [ -f "$out" ] && [ "$(stat -c%s "$out")" = "$want" ] && continue
    for try in 1 2 3 4 5 6 7 8; do
      curl -4 -s -o "$out.t" -r "$s-$e" --max-time 900 "$URL" 2>/dev/null
      got=$(stat -c%s "$out.t" 2>/dev/null || echo 0)
      if [ "$got" = "$want" ]; then mv "$out.t" "$out"; break; fi
      sleep $((try*4))
    done
    rm -f "$out.t" 2>/dev/null
  done < "$PARTS/jobs.txt"
}
export -f worker; export URL PARTS
for k in 1 2 3 4 5; do worker & done
wait
cat "$PARTS"/p???? > "$DST.tmp" 2>/dev/null
GOT=$(stat -c%s "$DST.tmp" 2>/dev/null || echo 0)
if [ "$GOT" = "$LEN" ] && [ "$(head -c2 "$DST.tmp")" = "OE" ]; then
  mv "$DST.tmp" "$DST"; echo "  [$FN] OK $GOT 字节"; exit 0
fi
echo "  [$FN] 合并校验失败 got=$GOT want=$LEN"; exit 1
