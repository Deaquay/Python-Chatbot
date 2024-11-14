@echo off

set "cwd=%~dp0"

echo ─────────────────────
echo Installing UV...
echo ─────────────────────

pip install -U UV

echo ─────────────────────
echo Installing VENV...
echo ─────────────────────

uv venv --seed .VENV

call %cwd%\.VENV\scripts\activate

echo ─────────────────────
echo Installing packages...
echo ─────────────────────

uv pip install setuptools wheel cohere

echo ─────────────────────
echo Done...
echo ─────────────────────
pause