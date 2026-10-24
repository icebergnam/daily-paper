#!/bin/sh
# 9008에 떠 있는 대시보드를 끄고 run.sh로 다시 띄운다(코드나 설정 파일을 고친 뒤 반영할 때).
cd "$(dirname "$0")" || exit 1
for p in $(lsof -nP -tiTCP:9008 -sTCP:LISTEN 2>/dev/null); do
  # 대시보드(python … scripts/….py 9008)만 끈다. macOS ps는 한글 파일 이름을 깨뜨려 보여 주므로 이름 대신 명령 모양으로 본다
  ps -o command= -p "$p" | grep -qi "python.* scripts/.*\.py 9008$" && kill "$p"
done
i=0
while lsof -nP -tiTCP:9008 -sTCP:LISTEN >/dev/null 2>&1; do
  i=$((i + 1))
  [ $i -gt 20 ] && echo "9008번을 다른 프로그램이 쓰고 있어 다시 띄우지 못했습니다." && exit 1
  sleep 0.25
done
exec ./run.sh
