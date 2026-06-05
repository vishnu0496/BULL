@echo off
schtasks /create /tn "BULL Terminal" /tr "%~dp0run_bull.bat" /sc onlogon /rl highest /f
echo BULL will now start automatically on Windows login.
pause
