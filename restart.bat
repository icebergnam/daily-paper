@echo off
rem 9008에 떠 있는 대시보드를 끄고 run.bat으로 다시 띄운다(코드나 설정 파일을 고친 뒤 반영할 때).
chcp 65001 >nul
cd /d "%~dp0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":9008 .*LISTENING"') do taskkill /pid %%p /f >nul 2>nul
timeout /t 1 /nobreak >nul
call run.bat
