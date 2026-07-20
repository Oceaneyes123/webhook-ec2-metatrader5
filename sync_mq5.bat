@echo off
python "%~dp0webhook\sync_mq5.py"
exit /b %errorlevel%
