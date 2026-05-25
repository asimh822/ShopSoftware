@echo off
title United Mobile — EPOS Launcher
cd /d "%~dp0"

echo Starting United Mobile API Server...
start "United Mobile API" cmd /k "python api_server.py"

timeout /t 2 /nobreak >nul

echo Starting United Mobile Desktop App...
start "United Mobile EPOS" cmd /k "python main.py"
