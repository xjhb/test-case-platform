@echo off
chcp 65001 >nul
title 测管平台-前端
cd /d D:\testmanage\frontend
echo Starting frontend on http://127.0.0.1:5173
echo Press Ctrl+C to stop.
call npm run dev
pause
