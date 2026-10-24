#!/bin/sh
# 대시보드를 http://127.0.0.1:9008 에 띄운다. 저장소에 workspace/가 있으면 그쪽(내 설정·결과)을 연다.
cd "$(dirname "$0")" || exit 1
[ -f workspace/scripts/대시보드.py ] && cd workspace
exec python3 scripts/대시보드.py 9008
