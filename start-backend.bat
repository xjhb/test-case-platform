@echo off
chcp 65001 >nul
title 测管平台-后端
cd /d D:\testmanage\backend
echo Starting backend on http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
echo Press Ctrl+C to stop.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
