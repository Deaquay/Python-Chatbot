@echo off
setlocal EnableDelayedExpansion

REM Comment out these lines to remove proxy.
REM set HTTP_PROXY=http://example.host:8080
REM set HTTPS_PROXY=%HTTP_PROXY%

REM Store the current working directory
set "cwd=%~dp0"	

REM Start option selection
:choose_option
echo Choose which AI to start by typing its number, or 0 to exit.

REM Iterate through all *_system.txt files in system folder and list the available AIs
set "index=1"
for %%f in (%cwd%\system\*_system.txt) do (
    set "charname=%%~nf"
    echo !index!. !charname:_system=!
    set "ai_!index!=!charname:_system=!"
    set /a index+=1
)

REM Display exit option
echo 0. Exit

REM Prompt user for choice
set /p choice="Enter the number of your choice (0 to exit): "

if "%choice%"=="0" (
    echo Exiting...
    exit /b 0
)

REM Set the character name based on the choice
set "charname="
for /l %%i in (1,1,!index!) do (
    if "!choice!"=="%%i" set "charname=!ai_%%i!"
)

if "%charname%"=="" (
    echo Invalid choice. Please try again.
    pause
    goto choose_option
)

REM Set up environment and run Cohere script
REM Backup API Keys, save date to know when it resets
REM ───────────────────────────────────────────────────────────────
REM tempmail1@example.com 	20-november 23456789-abcd-1234-efgh-56789ijklmno
REM tempmail2@example.com 	27-november 35648974-abcd-1234-efgh-56789ijklmno
REM tempmail3@example.com 	ACTIVE 		12345678-abcd-1234-efgh-56789ijklmno
REM ───────────────────────────────────────────────────────────────

set COHERE_API_KEY=xxxREPLACE-WITH-APIKEYxxxx
REM like this 
REM set COHERE_API_KEY=cWgXtmQS7Scs123wEnUpjh24hrFY4qJplzJGwVcx

if "%charname%"=="" (
    echo No AI selected, exiting...
    exit /b 1
)

PUSHD "%cwd%"
%cwd%\.VENV\scripts\python.exe %cwd%\.AI-Base.py %charname%
POPD

echo Press any key to return to the main menu...
pause
goto choose_option