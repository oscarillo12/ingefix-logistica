@echo off
cd /d "%~dp0"
title INGEFIX - Servidor local (mantener abierto)
echo Iniciando INGEFIX. Mantenga esta ventana abierta mientras use la aplicacion.
python app\server.py
if errorlevel 1 pause
