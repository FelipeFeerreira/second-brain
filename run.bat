@echo off
setlocal enabledelayedexpansion
title Segundo Cerebro
cd /d "%~dp0"

echo ============================================
echo   Segundo Cerebro - iniciando...
echo ============================================
echo.

rem --- Tenta achar o Python de varias formas, sem depender do PATH ---
set "PY="

where python >nul 2>nul
if not errorlevel 1 set "PY=python"

if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py"
)

if not defined PY (
    for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%d\python.exe" set "PY=%%d\python.exe"
    )
)

if not defined PY (
    echo [ERRO] Nao encontrei o Python instalado neste computador.
    echo.
    echo Baixe e instale em: https://www.python.org/downloads/
    echo IMPORTANTE: marque a caixa "Add python.exe to PATH" na primeira tela do instalador.
    echo Depois de instalar, feche esta janela e abra o run.bat de novo.
    echo.
    pause
    exit /b 1
)

echo Usando Python em: %PY%
"%PY%" --version
if errorlevel 1 (
    echo.
    echo [ERRO] Encontrei o Python mas nao consegui executa-lo. Reinstale o Python
    echo em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
echo.

echo Instalando dependencias (so demora na primeira vez)...
"%PY%" -m pip install --user -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar as dependencias ^(Flask, PyYAML, Markdown...^).
    echo Veja a mensagem de erro acima. Se falar de "pip" nao reconhecido,
    echo reinstale o Python marcando "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo.
echo Tudo certo! Abrindo o servidor...
echo Quando aparecer "Segundo Cerebro rodando!", abra no navegador:
echo   http://127.0.0.1:5000
echo.
echo (Para fechar o programa, feche esta janela ou aperte Ctrl+C)
echo.

"%PY%" app.py

echo.
echo O servidor foi encerrado.
pause
