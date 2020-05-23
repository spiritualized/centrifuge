@echo off
python -c "import sys; sys.exit(sys.version_info[0] < 3 or sys.version_info[1] < 3 )" 2>NUL
if errorlevel 1 goto errorNoPython
cd /d %~dp0
python -m venv venv-win
CALL venv-win/Scripts/activate.bat
pip install -r requirements.txt
pip install pyinstaller
echo Environment setup complete.

pyinstaller --additional-hooks-dir "hooks" %* -F centrifuge.py
cp  ini_template dist/ini_template
echo Build complete.
deactivate

echo Environment break down complete.
:errorNoPython
    echo Error^: Python > 3.3 not installed
