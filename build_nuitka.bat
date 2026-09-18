@echo off
setlocal
cd /d "%~dp0"

rem ===================================================
rem  SoloTalk Zhongkao build: Nuitka + Inno Setup
rem  NOTE: keep this file PURE ASCII and CRLF. Chinese
rem        text here crashes cmd on GBK systems.
rem ===================================================

rem ---- check Vosk model (single-line ifs only) ----
if exist "vosk-model-small-en-us-0.15\am\final.mdl" goto :have_model
echo [WARN] vosk-model-small-en-us-0.15 not found.
echo [WARN] Building WITHOUT voice auto-grading. Put the model folder here to enable it.
goto :after_model
:have_model
echo [OK] Vosk English model found, will be bundled.
set HAVE_MODEL=1
:after_model

echo.
echo ================================================
echo  [1/4] Installing build & runtime dependencies
echo ================================================
python -m pip install --upgrade pip
python -m pip install --upgrade nuitka ordered-set zstandard imageio
python -m pip install PyQt5 pyttsx3 sounddevice vosk pygame numpy scipy edge-tts
if errorlevel 1 goto :fail

rem ---- ensure clean entry file main.py ----
if exist "main.py" goto :have_main
for %%F in (SoloTalk*.py) do copy /y "%%F" "main.py" >nul
:have_main
if exist "main.py" goto :run_nuitka
echo [ERROR] cannot find the main python file (expect a SoloTalk*.py here).
goto :fail

:run_nuitka
echo.
echo ================================================
echo  [2/4] Nuitka standalone compile. First run is
echo        slow (compiles C). Please be patient.
echo ================================================
set FLAGS=--standalone --enable-plugin=pyqt5 --windows-console-mode=disable --output-dir=build
set FLAGS=%FLAGS% --include-package=vosk
set FLAGS=%FLAGS% --include-package=pygame
set FLAGS=%FLAGS% --include-package=sounddevice
set FLAGS=%FLAGS% --include-package=edge_tts
set FLAGS=%FLAGS% --include-package-data=edge_tts
set FLAGS=%FLAGS% --include-package=scipy
set FLAGS=%FLAGS% --include-package=numpy
set FLAGS=%FLAGS% --output-filename=SoloTalkZhongKao.exe
if defined HAVE_MODEL set FLAGS=%FLAGS% --include-data-dir=vosk-model-small-en-us-0.15=vosk-model-small-en-us-0.15

python -m nuitka %FLAGS% main.py
if errorlevel 1 goto :fail

set "DIST=build\main.dist"
if exist "%DIST%" goto :output_ok
echo [ERROR] build\main.dist was not created.
goto :fail
:output_ok
echo.
echo ================================================
echo  [3/4] Output folder: %DIST%
echo ================================================

rem ---- locate Inno Setup (6 or 7) ----
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if defined ISCC goto :have_iscc
echo [WARN] Inno Setup not found, skipping installer.
echo [WARN] Ship this folder instead: %DIST%
goto :done

:have_iscc
echo.
echo ================================================
echo  [4/4] Building installer with Inno: %ISCC%
echo ================================================
"%ISCC%" installer.iss
if errorlevel 1 echo [WARN] Inno compile failed (installer.iss). App folder is ready.

:done
echo.
echo DONE! App folder: %DIST%
if exist "installer\*.exe" echo Installer: installer\
pause
exit /b 0

:fail
echo.
echo [ERROR] build failed. See messages above.
pause
exit /b 1