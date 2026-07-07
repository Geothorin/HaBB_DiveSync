@echo off
title ROV Sync Tool - Installazione
color 0A
echo.
echo  =========================================
echo   ROV Sync Tool v1.0 - Installazione
echo  =========================================
echo.

REM Controlla se Python e' installato
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    color 0C
    echo  [ERRORE] Python non trovato sul tuo computer.
    echo.
    echo  Devi installare Python prima di continuare.
    echo  1. Apri il browser e vai su: https://www.python.org/downloads/
    echo  2. Clicca sul bottone giallo "Download Python"
    echo  3. Avvia il file scaricato
    echo  4. IMPORTANTE: spunta la casella "Add Python to PATH"
    echo  5. Clicca "Install Now"
    echo  6. Riavvia questo file install.bat
    echo.
    pause
    exit /b 1
)

echo  [OK] Python trovato:
python --version
echo.

REM Aggiorna pip
echo  Aggiornamento pip...
python -m pip install --upgrade pip --quiet
echo  [OK] pip aggiornato.
echo.

REM Installa dipendenze
echo  Installazione librerie necessarie...
echo  (potrebbe volerci qualche minuto, attendere)
echo.
python -m pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    color 0C
    echo.
    echo  [ERRORE] Installazione fallita.
    echo  Controlla la connessione internet e riprova.
    pause
    exit /b 1
)

echo.
echo  =========================================
echo   Installazione completata con successo!
echo  =========================================
echo.
echo  Ora puoi avviare il programma con:
echo  -> Doppio click su "avvia_rov_tool.bat"
echo.
pause
