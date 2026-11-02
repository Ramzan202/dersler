@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Otomatik Ders Dagilim Programi

echo ============================================================
echo   Otomatik Ders Dagilim Programi
echo ============================================================

rem ---- 1. Python 3.11+ kontrolu ------------------------------------------
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
        if not errorlevel 1 set "PY=python"
    )
)
if not defined PY goto :no_python

rem ---- 2. Sanal ortam (venv) ---------------------------------------------
if exist "venv\Scripts\python.exe" goto :venv_ready
echo [1/3] Sanal ortam olusturuluyor (venv)...
%PY% -m venv venv
if errorlevel 1 goto :venv_failed
:venv_ready
set "VPY=venv\Scripts\python.exe"

"%VPY%" -c "import tkinter" >nul 2>nul
if errorlevel 1 goto :no_tk

rem ---- 3. Bagimliliklar (yalnizca eksikse veya requirements.txt degistiyse) ---
"%VPY%" scripts\check_requirements.py >nul 2>nul
if not errorlevel 1 goto :deps_ready

rem ---- 3b. OR-Tools gercekten yukleniyor mu? (Visual C++ Redistributable gerekir) ----
"%VPY%" -m app.utils.native_libs >nul 2>nul
if not errorlevel 1 goto :solver_ok
echo.
echo [UYARI] Optimizasyon kutuphanesi (OR-Tools) yuklenemedi.
echo         Genellikle "Microsoft Visual C++ Redistributable" eksik oldugunda olur.
choice /C EH /M "Simdi indirilip kurulsun mu? (E=Evet, H=Hayir)"
if errorlevel 2 goto :solver_skip
echo Indiriliyor: https://aka.ms/vs/17/release/vc_redist.x64.exe
curl -L -s -o "%TEMP%\vc_redist.x64.exe" https://aka.ms/vs/17/release/vc_redist.x64.exe
if errorlevel 1 goto :vc_failed
echo Kurulum baslatiliyor (yonetici izni istenebilir)...
"%TEMP%\vc_redist.x64.exe" /install /passive /norestart
"%VPY%" -m app.utils.native_libs >nul 2>nul
if not errorlevel 1 goto :solver_ok
:vc_failed
echo.
echo [UYARI] Sorun devam ediyor. Bilgisayari yeniden baslatip run.bat'i tekrar calistirin.
echo         Yine olmazsa Python 3.12 kurun, "venv" klasorunu silin ve run.bat'i yeniden calistirin.
echo         Program yine de acilacak; veriler girilebilir, otomatik dagitim calismaz.
pause
:solver_skip
:solver_ok
echo [2/3] Gerekli kutuphaneler yukleniyor. Ilk kurulumda internet gerekir, birkac dakika surebilir...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check -q
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_failed
"%VPY%" scripts\check_requirements.py --stamp
"%VPY%" scripts\check_requirements.py
if errorlevel 1 goto :pip_failed
:deps_ready

rem ---- 4. Uygulamayi baslat ----------------------------------------------
echo [3/3] Program baslatiliyor...
"%VPY%" main.py
if errorlevel 1 goto :app_failed
exit /b 0

:no_python
echo.
echo [HATA] Python 3.11 veya daha yeni bir surum bulunamadi.
echo   1. https://www.python.org/downloads/ adresinden Python 3.11+ indirin.
echo   2. Kurulumda "Add python.exe to PATH" ve "tcl/tk and IDLE" seceneklerini isaretleyin.
echo   3. Kurulumdan sonra run.bat dosyasini yeniden calistirin.
pause
exit /b 1

:venv_failed
echo.
echo [HATA] Sanal ortam olusturulamadi. Klasorun yazilabilir oldugundan emin olun
echo        ve Python kurulumunu "Repair" ile onarin.
pause
exit /b 1

:no_tk
echo.
echo [HATA] Python kurulumunda grafik arayuz destegi (tkinter) yok.
echo        Python kurulumunu "Modify" ile acip "tcl/tk and IDLE" secenegini isaretleyin,
echo        ardindan "venv" klasorunu silip run.bat dosyasini yeniden calistirin.
pause
exit /b 1

:pip_failed
echo.
echo [HATA] Kutuphaneler yuklenemedi. Internet baglantinizi kontrol edin
echo        ve run.bat dosyasini yeniden calistirin. Sorun surerse "venv" klasorunu silin.
pause
exit /b 1

:app_failed
echo.
echo [HATA] Program beklenmedik sekilde kapandi. Ayrintilar: data\hata_kaydi.log
pause
exit /b 1
