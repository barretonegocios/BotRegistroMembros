@echo off
title Bot Registro de Membros
:loop
echo Iniciando BotRegistro...
python botregistro.py
echo Bot encerrado. Reiniciando em 5 segundos...
timeout /t 5
goto loop
