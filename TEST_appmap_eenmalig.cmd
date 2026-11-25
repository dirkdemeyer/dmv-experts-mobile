@echo off
chcp 65001 >nul
set "INBOX=C:\Users\Dirk De Meyer\Dropbox\Apps\DMVExpertsMobile\DMV_TRANSFER"
if not exist "%INBOX%" (
 echo De map bestaat nog niet: %INBOX%
 echo Koppel eerst de mobiele app en upload een testdossier.
 pause
 exit /b 1
)
cd /d "%~dp0"
python DMV_PC_ontvanger.py --inbox "%INBOX%" --once
pause
