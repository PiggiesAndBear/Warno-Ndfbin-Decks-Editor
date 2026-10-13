@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem Find an interpreter without naming anybody's folder.  This file ships with
rem the repository, so a hard-coded path would make it work on exactly one
rem computer -- and would publish that computer's user name to everyone else.
rem
rem Order: a virtualenv next to this script first, then whatever Python the
rem machine has.  Existence is enough to choose between them; whether an
rem interpreter can actually run the editor is checked separately below, in
rem one place, because "which Python" and "which Python has the dependencies"
rem are different questions and a machine can easily have three of the former
rem and none of the latter.
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
  py -3 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  python -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython

rem One dependency check instead of four probes: the error below can then name
rem exactly what is missing and how to install it, rather than surfacing as a
rem ModuleNotFoundError traceback in a console window that closes.
%PY% -c "import PySide6, zstandard, lz4" >nul 2>&1
if errorlevel 1 goto nodeps

%PY% main.py
if errorlevel 1 goto failed
exit /b 0

:nopython
echo 没有找到 Python。
echo 需要 Python 3.10 或更高版本，网址 python.org。装好后重新运行本文件。
echo.
echo 如果已经装了但这里找不到，也可以手动执行：
echo     python main.py
echo.
pause
exit /b 1

:nodeps
echo 找到了 Python（%PY%），但它缺少运行所需的库：
echo     PySide6、zstandard、lz4
echo.
echo 在本目录执行下面两行安装（只需做一次）：
echo.
echo     %PY% -m venv .venv
echo     .venv\Scripts\pip install -r requirements.txt
echo.
echo 装完重新运行本文件即可 —— 它会自动优先使用 .venv。
echo.
pause
exit /b 1

:failed
echo.
echo 启动失败。上面的报错信息一般已经说明了原因。
echo.
pause
exit /b 1
