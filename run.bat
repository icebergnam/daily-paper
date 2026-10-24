@echo off
rem 대시보드를 http://127.0.0.1:9008 에 띄운다. 저장소에 workspace\가 있으면 그쪽(내 설정·결과)을 연다.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist "workspace\scripts\대시보드.py" cd workspace
set PY=python
where python >nul 2>nul || set PY=py -3
%PY% scripts\대시보드.py 9008
pause
