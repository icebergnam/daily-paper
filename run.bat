@echo off
rem 대시보드를 http://127.0.0.1:9008 에 띄운다. 코드는 이 저장소, 내 설정·결과는 workspace\에서 읽는다.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py -3
%PY% scripts\대시보드.py 9008
pause
