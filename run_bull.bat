@echo off
title BULL Terminal
cd /d %~dp0
echo Starting BULL...
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
pause
