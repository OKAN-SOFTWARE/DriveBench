@echo off
setlocal
cd /d "%~dp0"
where java >nul 2>nul
if errorlevel 1 goto missingjava
where mvn >nul 2>nul
if errorlevel 1 goto missingmaven
where python >nul 2>nul
if errorlevel 1 goto missingpython
call mvn -B -f simulator\pom.xml verify
if errorlevel 1 goto buildfailed
python start.py --no-build
if errorlevel 1 pause
exit /b
:missingjava
echo Java 17 or newer is required. Install a JDK and reopen your terminal.
pause
exit /b 1
:missingmaven
echo Maven 3.9 or newer is required. Add Maven's bin directory to PATH and reopen your terminal.
pause
exit /b 1
:missingpython
echo Python 3.11 or newer is required. Install Python with Add Python to PATH enabled.
pause
exit /b 1
:buildfailed
echo Java build failed. Read the Maven error above. See README.md for troubleshooting.
pause
exit /b 1
