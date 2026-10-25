#!/bin/sh
# 대시보드를 http://127.0.0.1:9008 에 띄운다. 코드는 이 저장소, 내 설정·결과는 workspace/에서 읽는다.
cd "$(dirname "$0")" || exit 1
exec python3 scripts/대시보드.py 9008
