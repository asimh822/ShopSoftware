@echo off
title United Mobile — API Server
echo Starting United Mobile API Server on port 5000...
cd /d "%~dp0"
python api_server.py
pause
