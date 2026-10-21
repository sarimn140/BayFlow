@echo off
rem stop.bat - stop the BayFlow local dev stack on Windows and free ports 3000 and 4000.
rem D73, spec 07. Linux and macOS: stop.sh. start.bat calls this script to clean up stale state.
rem   1. stop the process trees recorded by start.bat in .run\api.pid and .run\web.pid,
rem      after checking that each PID still belongs to python, uv, uvicorn or node
rem   2. close the windows titled "BayFlow API" and "BayFlow Web" with their process trees
rem   3. stop BayFlow's own Docker api and web containers if they run - docker compose up
rem   4. port backstop: stop whatever still listens on 4000 and 3000, never Docker's port
rem      forwarders. With --bayflow-only only processes whose command line contains this folder.
rem   5. remove the Next.js dev lock state apps\web\.next\dev and apps\web\.next\lock, and the PID files
rem   6. docker compose stop db unless --keep-db. The data volume is always kept.
rem   7. verify that ports 3000 and 4000 are free; otherwise name the holder and exit with code 1
rem Keeps going when a step fails and is safe to run twice.
rem Usage: stop.bat [--keep-db] [--quiet] [--bayflow-only] [--help]
setlocal EnableExtensions EnableDelayedExpansion
rem The folder name may contain parentheses: change to it once and use relative paths only.
cd /d "%~dp0"
if errorlevel 1 goto :err_cd
set "ROOT=%CD%"
set "KEEP_DB=0"
set "QUIET=0"
set "BAYFLOW_ONLY=0"

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--keep-db" (set "KEEP_DB=1" & shift & goto :parse_args)
if /i "%~1"=="--quiet" (set "QUIET=1" & shift & goto :parse_args)
if /i "%~1"=="--bayflow-only" (set "BAYFLOW_ONLY=1" & shift & goto :parse_args)
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-h" goto :usage
echo [FAIL] Unknown option: "%~1"
echo.
call :print_usage
exit /b 2
:args_done

if "%QUIET%"=="0" echo.
if "%QUIET%"=="0" echo Stopping BayFlow...

rem 1. Process trees recorded by start.bat
call :stop_recorded api
call :stop_recorded web

rem 2. Windows titled by start.bat. Best effort: Windows Terminal tabs may not expose the title.
taskkill /F /T /FI "WINDOWTITLE eq BayFlow API*" >nul 2>&1
taskkill /F /T /FI "WINDOWTITLE eq BayFlow Web*" >nul 2>&1

rem 3. Docker: BayFlow's own api and web containers publish ports 3000 and 4000
set "DOCKER_UP=0"
where docker >nul 2>&1
if errorlevel 1 goto :docker_checked
docker info >nul 2>&1
if errorlevel 1 goto :docker_checked
set "DOCKER_UP=1"
set "APP_CONTAINERS="
for /f "delims=" %%S in ('docker compose -f docker-compose.yml -p bayflow ps --status running --services 2^>nul') do (
  if /i "%%S"=="api" set "APP_CONTAINERS=!APP_CONTAINERS! api"
  if /i "%%S"=="web" set "APP_CONTAINERS=!APP_CONTAINERS! web"
)
if not defined APP_CONTAINERS goto :docker_checked
echo [WARN] Stopping BayFlow's Docker containers:%APP_CONTAINERS% - they publish ports 3000 and 4000
docker compose -f docker-compose.yml -p bayflow stop%APP_CONTAINERS% >nul 2>&1
:docker_checked

rem 4. Port backstop, twice: a parent process may restart a killed child
call :free_port 4000
call :free_port 3000
ping -n 2 127.0.0.1 >nul
call :free_port 4000
call :free_port 3000

rem 5. Next.js dev lock state - a stale lock stops the next "next dev" - and the PID files
if exist "apps\web\.next\dev\" rmdir /s /q "apps\web\.next\dev" >nul 2>&1
if exist "apps\web\.next\lock\" rmdir /s /q "apps\web\.next\lock" >nul 2>&1
if exist "apps\web\.next\lock" del /f /q "apps\web\.next\lock" >nul 2>&1
if exist ".run\api.pid" del /f /q ".run\api.pid" >nul 2>&1
if exist ".run\web.pid" del /f /q ".run\web.pid" >nul 2>&1
if exist ".run\pids" del /f /q ".run\pids" >nul 2>&1

rem 6. PostgreSQL container; its data volume is kept
if "%KEEP_DB%"=="1" goto :db_done
if "%DOCKER_UP%"=="0" goto :db_no_docker
if "%QUIET%"=="0" echo   db container: stopping - the data volume is kept
docker compose -f docker-compose.yml -p bayflow stop db >nul 2>&1
if errorlevel 1 echo [WARN] docker compose stop db failed - check: docker compose ps
goto :db_done
:db_no_docker
echo [WARN] Docker is not running or not installed - the db container was not stopped.
:db_done

rem 7. Verify
set "BUSY="
call :port_pids 4000
if defined PORT_PIDS set "BUSY=!BUSY! 4000"
call :port_pids 3000
if defined PORT_PIDS set "BUSY=!BUSY! 3000"
if not defined BUSY goto :all_free
for %%P in (%BUSY%) do call :describe_port %%P
if "%BAYFLOW_ONLY%"=="1" echo [FAIL] BayFlow needs ports 3000 and 4000. Stop that program, or run stop.bat, which stops whatever listens there.
exit /b 1

:all_free
if "%QUIET%"=="1" exit /b 0
if "%KEEP_DB%"=="1" goto :all_free_keep_db
echo [ OK ] BayFlow stopped. Ports 3000 and 4000 are free. Data kept; wipe it with: make db-reset
exit /b 0
:all_free_keep_db
echo [ OK ] BayFlow stopped. Ports 3000 and 4000 are free; PostgreSQL left running.
exit /b 0

rem ---------------------------------------------------------------------------------------------
rem Subroutines. Every one ends with exit /b.

:stop_recorded
rem Argument: api or web. Stops the process tree whose PID start.bat wrote to .run\NAME.pid
if not exist ".run\%~1.pid" exit /b 0
set "RPID="
set /p RPID=<".run\%~1.pid"
if not defined RPID exit /b 0
call :proc_name %RPID%
if /i "!PNAME!"=="python.exe" goto :stop_recorded_kill
if /i "!PNAME!"=="pythonw.exe" goto :stop_recorded_kill
if /i "!PNAME!"=="uvicorn.exe" goto :stop_recorded_kill
if /i "!PNAME!"=="uv.exe" goto :stop_recorded_kill
if /i "!PNAME!"=="node.exe" goto :stop_recorded_kill
if "%QUIET%"=="0" echo   %~1: PID %RPID% is not running any more
exit /b 0
:stop_recorded_kill
if "%QUIET%"=="0" echo   %~1: stopping PID %RPID% and its child processes
taskkill /F /T /PID %RPID% >nul 2>&1
exit /b 0

:proc_name
rem Argument: a PID. Sets PNAME to its image name, for example node.exe, or to "unknown".
set "PNAME="
for /f "tokens=1 delims=," %%N in ('tasklist /FI "PID eq %~1" /FO CSV /NH 2^>nul') do set "PNAME=%%~N"
if not defined PNAME set "PNAME=unknown"
if /i "!PNAME:~0,5!"=="INFO:" set "PNAME=unknown"
exit /b 0

:is_ours
rem Argument: a PID. Sets IS_OURS=1 when its command line contains this folder, otherwise 0.
set "IS_OURS=0"
set "PCMD="
for /f "usebackq delims=" %%C in (`powershell -NoProfile -NonInteractive -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=%~1').CommandLine" 2^>nul`) do set "PCMD=%%C"
if not defined PCMD exit /b 0
if /i not "!PCMD:%ROOT%=!"=="!PCMD!" set "IS_OURS=1"
exit /b 0

:port_pids
rem Argument: a port. Sets PORT_PIDS to " pid1 pid2 ", the PIDs listening on it over IPv4 or IPv6,
rem or leaves it undefined when nothing listens. ":3000 " never matches ":30000".
rem Besides the LISTENING state, which is localised on some Windows languages, a listener
rem is recognised by its foreign address 0.0.0.0:0 or [::]:0.
set "PORT_PIDS="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING" /C:":%~1  *0\.0\.0\.0:0 " /C:":%~1  *\[::\]:0 "') do call :add_port_pid %%P
exit /b 0

:add_port_pid
if "%~1"=="0" exit /b 0
if not defined PORT_PIDS (set "PORT_PIDS= %~1 " & exit /b 0)
if "!PORT_PIDS: %~1 =!"=="!PORT_PIDS!" set "PORT_PIDS=!PORT_PIDS!%~1 "
exit /b 0

:free_port
rem Argument: a port. Stops what listens on it.
call :port_pids %1
if not defined PORT_PIDS exit /b 0
for %%P in (%PORT_PIDS%) do call :kill_listener %%P %1
exit /b 0

:kill_listener
rem Arguments: PID and port. Never the System process or Docker and WSL port forwarders.
if "%~1"=="4" exit /b 0
call :proc_name %1
if /i "!PNAME:~0,10!"=="com.docker" exit /b 0
if /i "!PNAME!"=="wslrelay.exe" exit /b 0
if /i "!PNAME!"=="vpnkit.exe" exit /b 0
if /i "!PNAME!"=="dockerd.exe" exit /b 0
if /i "!PNAME!"=="docker-proxy.exe" exit /b 0
if "%BAYFLOW_ONLY%"=="0" goto :kill_listener_now
call :is_ours %1
if "!IS_OURS!"=="0" exit /b 0
:kill_listener_now
echo [WARN] Port %~2 is held by !PNAME! PID %~1 - stopping it
taskkill /F /T /PID %~1 >nul 2>&1
exit /b 0

:describe_port
rem Argument: a port. Prints who holds it.
call :port_pids %1
if not defined PORT_PIDS exit /b 0
for %%P in (%PORT_PIDS%) do call :describe_pid %%P %1
exit /b 0

:describe_pid
rem Arguments: PID and port
call :proc_name %1
if "%~1"=="4" goto :describe_pid_system
if /i "!PNAME:~0,10!"=="com.docker" goto :describe_pid_docker
if /i "!PNAME!"=="wslrelay.exe" goto :describe_pid_docker
if /i "!PNAME!"=="vpnkit.exe" goto :describe_pid_docker
echo [FAIL] Port %~2 is still in use by !PNAME!, PID %~1
exit /b 0
:describe_pid_system
echo [FAIL] Port %~2 is still in use by Windows itself, System PID 4 - for example IIS or HTTP.sys
exit /b 0
:describe_pid_docker
echo [FAIL] Port %~2 is still in use by a Docker or WSL port forward - see: docker ps
exit /b 0

:usage
call :print_usage
exit /b 0

:print_usage
echo Usage: stop.bat [--keep-db] [--quiet] [--bayflow-only] [--help]
echo.
echo Stops the BayFlow dev stack started by start.bat and frees ports 3000 and 4000.
echo.
echo   --keep-db       leave the PostgreSQL container running
echo   --quiet         print only problems
echo   --bayflow-only  stop only BayFlow's own processes; if another program holds port 3000
echo                   or 4000, name it and exit with code 1 instead. Not used by start.bat,
echo                   which frees the ports from any program.
echo   --help          show this help
echo.
echo The database volume is always kept. To wipe the local data use: make db-reset
exit /b 0

:err_cd
echo [FAIL] Cannot change to the folder of stop.bat.
exit /b 1
