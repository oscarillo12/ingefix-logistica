@echo off
cd /d "%~dp0"
title INGEFIX - Acceso movil (mantener abierto)
echo Iniciando acceso movil. Mantenga esta ventana abierta.
python app\server.py --lan
if errorlevel 1 pause
