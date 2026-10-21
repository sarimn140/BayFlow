@echo off
rem start.bat - start the BayFlow local dev stack on Windows. D73, spec 07. Linux and macOS: start.sh
rem   1. preflight: docker with Compose v2 and a running daemon, uv, node 24 or newer, pnpm, curl
rem   2. create .env from .env.example if missing, then load it into this console
rem   3. install dependencies if missing: uv sync in apps\api, pnpm install in apps\web
rem   4. free the ports: stop.bat --keep-db --quiet stops stale BayFlow processes and ANY other
rem      program listening on port 3000 or 4000, named in the output.
rem   5. docker compose up -d --wait db, host port POSTGRES_HOST_PORT, default 5434
rem   6. uv run alembic upgrade head, then uv run python -m app.scripts.seed. The seed acts only
rem      when SEED_ON_DEPLOY=true, which .env.example sets; --seed adds --force.
rem   7. start the API on port 4000 and the web app on port 3000, each in a minimized window titled
rem      "BayFlow API" or "BayFlow Web", output in logs\api.log and logs\web.log
rem   8. wait for http://localhost:4000/health and http://localhost:3000, record the listening
rem      PIDs in .run\api.pid and .run\web.pid, print the URLs. On failure: show the last
rem      log lines and run stop.bat.
rem   9. unless --detach: press any key in this window to stop everything with stop.bat
rem Usage: start.bat [--detach] [--seed] [--no-install] [--help]
setlocal EnableExtensions DisableDelayedExpansion
rem The folder name may contain parentheses: change to it once and use relative paths only.
cd /d "%~dp0"
if errorlevel 1 goto :err_cd
set "ROOT=%CD%"
set "SCRIPT_NAME=%~nx0"
set "DETACH=0"
set "SEED=0"
set "INSTALL=1"

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--detach" (set "DETACH=1" & shift & goto :parse_args)
if /i "%~1"=="--seed" (set "SEED=1" & shift & goto :parse_args)
if /i "%~1"=="--no-install" (set "INSTALL=0" & shift & goto :parse_args)
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-h" goto :usage
echo [FAIL] Unknown option: "%~1"
echo.
call :print_usage
exit /b 2
:args_done

echo.
echo   BayFlow - local dev stack
echo   -------------------------

rem 2. .env: created from .env.example on the first run, then loaded into this console.
rem Delayed expansion is still off here, so values may contain exclamation marks.
if exist ".env" goto :env_exists
if not exist ".env.example" goto :err_no_env_example
copy /y ".env.example" ".env" >nul
if errorlevel 1 goto :err_env_copy
echo [WARN] Created .env from .env.example with local defaults - edit it if you need other values.
:env_exists
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do set "%%A=%%~B"
echo [ OK ] Loaded .env

setlocal EnableExtensions EnableDelayedExpansion
if not defined POSTGRES_HOST_PORT set "POSTGRES_HOST_PORT=5434"
rem Started by a double click? Then pause before the window closes so messages stay readable.
set "PAUSE_ON_EXIT=0"
if /i not "!CMDCMDLINE:%SCRIPT_NAME%=!"=="!CMDCMDLINE!" set "PAUSE_ON_EXIT=1"

rem 1. Preflight
echo.
echo [....] Checking prerequisites
where docker >nul 2>&1
if errorlevel 1 goto :err_docker_missing
docker compose version >nul 2>&1
if errorlevel 1 goto :err_compose_missing
docker info >nul 2>&1
if errorlevel 1 goto :err_docker_down
where uv >nul 2>&1
if errorlevel 1 goto :err_uv_missing
where node >nul 2>&1
if errorlevel 1 goto :err_node_missing
set "NODE_MAJOR=0"
for /f "tokens=1 delims=.v" %%V in ('node --version 2^>nul') do set "NODE_MAJOR=%%V"
if !NODE_MAJOR! LSS 24 goto :err_node_old
where pnpm >nul 2>&1
if errorlevel 1 goto :err_pnpm_missing
where curl >nul 2>&1
if errorlevel 1 goto :err_curl_missing
if not exist "apps\api\pyproject.toml" goto :err_no_api
if not exist "apps\web\package.json" goto :err_no_web
echo [ OK ] docker, uv, node !NODE_MAJOR!, pnpm and curl found

rem 3. Dependencies
set "UV_RUN=uv run"
if "%INSTALL%"=="0" goto :deps_no_install
if exist "apps\api\.venv\" goto :api_deps_ok
echo [....] Installing API dependencies: uv sync
pushd "apps\api"
uv sync
set "RC=!ERRORLEVEL!"
popd
if not "!RC!"=="0" goto :err_uv_sync
:api_deps_ok
if exist "apps\web\node_modules\" goto :deps_ok
echo [....] Installing web dependencies: pnpm install
pushd "apps\web"
call pnpm install
set "RC=!ERRORLEVEL!"
popd
if not "!RC!"=="0" goto :err_pnpm_install
goto :deps_ok
:deps_no_install
set "UV_RUN=uv run --no-sync"
if not exist "apps\api\.venv\" goto :err_no_venv
if not exist "apps\web\node_modules\" goto :err_no_node_modules
:deps_ok
echo [ OK ] Dependencies present

rem 4. Stale BayFlow processes, busy ports, Next.js dev lock
echo [....] Stopping stale processes and freeing ports 3000 and 4000
call "%ROOT%\stop.bat" --keep-db --quiet
if errorlevel 1 goto :err_ports
echo [ OK ] Ports 3000 and 4000 are free

rem 5. PostgreSQL in Docker
echo [....] Starting PostgreSQL 16 in Docker on localhost:!POSTGRES_HOST_PORT!
docker compose -f docker-compose.yml -p bayflow up -d --wait --wait-timeout 90 db
if errorlevel 1 goto :err_db
echo [ OK ] PostgreSQL is healthy

rem 6. Migrations, then the seed script
echo [....] Applying database migrations: alembic upgrade head
pushd "apps\api"
%UV_RUN% alembic upgrade head
set "RC=!ERRORLEVEL!"
popd
if not "!RC!"=="0" goto :err_migrate
set "SEED_ARGS="
if "%SEED%"=="1" set "SEED_ARGS=--force"
echo [....] Running the seed script: python -m app.scripts.seed !SEED_ARGS! - it acts only when SEED_ON_DEPLOY=true or with --seed
pushd "apps\api"
%UV_RUN% python -m app.scripts.seed !SEED_ARGS!
set "RC=!ERRORLEVEL!"
popd
if not "!RC!"=="0" goto :err_seed
echo [ OK ] Database ready

rem 7. API and web, each in its own minimized window; output goes to logs\*.log
if not exist "logs\" mkdir "logs"
if not exist ".run\" mkdir ".run"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
echo [....] Starting the API and the web app in minimized windows "BayFlow API" and "BayFlow Web"
start "BayFlow API" /min /d "%ROOT%\apps\api" cmd /d /s /c "%UV_RUN% uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload > ..\..\logs\api.log 2>&1"
rem .env sets PORT=4000 for the API; next dev also honours PORT, so the web window gets 3000.
set "PORT=3000"
start "BayFlow Web" /min /d "%ROOT%\apps\web" cmd /d /s /c "call pnpm dev > ..\..\logs\web.log 2>&1"

rem 8. Health
echo [....] Waiting for the API: http://localhost:4000/health
set /a WAITED=0
:wait_api
curl -fsS -o nul --max-time 5 http://127.0.0.1:4000/health >nul 2>&1
if not errorlevel 1 goto :api_up
set /a WAITED+=1
if !WAITED! GEQ 90 goto :err_api_timeout
ping -n 2 127.0.0.1 >nul
goto :wait_api
:api_up
echo [ OK ] API is healthy

echo [....] Waiting for the web app: http://localhost:3000 - the first compile can take a while
set /a WAITED=0
:wait_web
curl -sS -o nul --max-time 20 http://127.0.0.1:3000/ >nul 2>&1
if not errorlevel 1 goto :web_up
set /a WAITED+=1
if !WAITED! GEQ 120 goto :err_web_timeout
ping -n 2 127.0.0.1 >nul
goto :wait_web
:web_up
echo [ OK ] Web app is up

call :port_pids 4000
call :write_pid api
call :port_pids 3000
call :write_pid web

rem 9. URLs
set "MAILPIT_UP="
for /f "delims=" %%M in ('docker ps -q --filter "label=com.docker.compose.project=bayflow" --filter "label=com.docker.compose.service=mailpit" --filter "status=running" 2^>nul') do set "MAILPIT_UP=1"
echo.
echo   BayFlow is running
echo   ------------------
echo   Web app ....... http://localhost:3000
echo   API docs ...... http://localhost:4000/docs
echo   API health .... http://localhost:4000/health
if defined MAILPIT_UP echo   Mailpit ....... http://localhost:8025
echo   PostgreSQL .... localhost:!POSTGRES_HOST_PORT!  - database, user and password: bayflow
echo   Logs .......... logs\api.log and logs\web.log
echo   Stop .......... stop.bat
if "%SEED%"=="1" goto :demo_hint
if /i "!SEED_ON_DEPLOY!"=="true" goto :demo_hint
echo   SEED_ON_DEPLOY is not true in .env, so no demo data was loaded: start.bat --seed
goto :after_hint
:demo_hint
echo   Demo logins ... password BayFlow@2026, e.g. bilal.sa@bayflow.test - all accounts in README.md
:after_hint
echo.

if "%DETACH%"=="0" goto :wait_for_key
echo [ OK ] Started in the background with --detach. Stop with stop.bat
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 0

:wait_for_key
echo Press any key in this window to stop BayFlow.
echo Closing the window instead leaves it running; stop it later with stop.bat.
echo If Ctrl+C asks "Terminate batch job (Y/N)?", answer N to stop BayFlow cleanly.
pause >nul
echo.
echo Stopping BayFlow...
call "%ROOT%\stop.bat"
exit /b 0

rem ---------------------------------------------------------------------------------------------
rem Subroutines. Every one ends with exit /b.

:port_pids
rem Argument: a port. Sets PORT_PIDS to " pid1 pid2 ", the PIDs listening on it over IPv4 or IPv6,
rem or leaves it undefined when nothing listens. ":3000 " never matches ":30000". Besides the
rem LISTENING state, which is localised on some Windows languages, a listener is recognised by
rem its foreign address 0.0.0.0:0 or [::]:0.
set "PORT_PIDS="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING" /C:":%~1  *0\.0\.0\.0:0 " /C:":%~1  *\[::\]:0 "') do call :add_port_pid %%P
exit /b 0

:add_port_pid
if "%~1"=="0" exit /b 0
if not defined PORT_PIDS (set "PORT_PIDS= %~1 " & exit /b 0)
if "!PORT_PIDS: %~1 =!"=="!PORT_PIDS!" set "PORT_PIDS=!PORT_PIDS!%~1 "
exit /b 0

:write_pid
rem Argument: api or web. Writes the first PID of PORT_PIDS to .run\NAME.pid for stop.bat.
if not defined PORT_PIDS exit /b 0
for %%P in (%PORT_PIDS%) do (
  >".run\%~1.pid" echo %%P
  exit /b 0
)
exit /b 0

:show_log
rem Argument: api or web. Prints the last 40 lines of logs\NAME.log.
echo.
echo ---- last 40 lines of logs\%~1.log ----
if not exist "logs\%~1.log" goto :show_log_missing
powershell -NoProfile -NonInteractive -Command "Get-Content -LiteralPath 'logs\%~1.log' -Tail 40" 2>nul
if errorlevel 1 type "logs\%~1.log"
echo ---- end of logs\%~1.log ----
echo.
exit /b 0
:show_log_missing
echo logs\%~1.log does not exist
exit /b 0

:usage
call :print_usage
exit /b 0

:print_usage
echo Usage: start.bat [--detach] [--seed] [--no-install] [--help]
echo.
echo Starts PostgreSQL 16 in Docker, applies the migrations, runs the seed script, then runs the
echo API on http://localhost:4000 and the web app on http://localhost:3000.
echo.
echo   --detach      return after starting; otherwise a key press in this window stops BayFlow
echo   --seed        load the demo data even when SEED_ON_DEPLOY is not true - seed --force
echo   --no-install  never install dependencies; fail if apps\api\.venv or apps\web\node_modules is missing
echo   --help        show this help
echo.
echo Logs: logs\api.log and logs\web.log. PIDs: .run\api.pid and .run\web.pid. Stop: stop.bat
exit /b 0

rem ---------------------------------------------------------------------------------------------
rem Errors. Each prints its message and jumps to :fail or :fail_stop.

:err_cd
echo [FAIL] Cannot change to the folder of start.bat.
exit /b 1

:err_no_env_example
echo [FAIL] .env.example is missing - cannot create .env.
goto :fail

:err_env_copy
echo [FAIL] Could not copy .env.example to .env.
goto :fail

:err_docker_missing
echo [FAIL] docker was not found. Install Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/
goto :fail

:err_compose_missing
echo [FAIL] Docker Compose v2 was not found - "docker compose" is required, not docker-compose v1.
goto :fail

:err_docker_down
echo [FAIL] Docker is installed but not running. Start Docker Desktop and try again.
goto :fail

:err_uv_missing
echo [FAIL] uv was not found. Install it: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
goto :fail

:err_node_missing
echo [FAIL] node was not found. Install Node.js 24 LTS: https://nodejs.org/
goto :fail

:err_node_old
echo [FAIL] Node.js !NODE_MAJOR! found - Node.js 24 LTS or newer is required: https://nodejs.org/
goto :fail

:err_pnpm_missing
echo [FAIL] pnpm was not found. Run: npm install -g pnpm@10.34.6   or, in an administrator prompt: corepack enable pnpm
goto :fail

:err_curl_missing
echo [FAIL] curl was not found. It ships with Windows 10 1803 and newer - check your PATH.
goto :fail

:err_no_api
echo [FAIL] apps\api\pyproject.toml is missing - is the checkout complete?
goto :fail

:err_no_web
echo [FAIL] apps\web\package.json is missing - is the checkout complete?
goto :fail

:err_uv_sync
echo [FAIL] uv sync failed in apps\api - see the messages above.
goto :fail

:err_pnpm_install
echo [FAIL] pnpm install failed in apps\web - see the messages above.
goto :fail

:err_no_venv
echo [FAIL] apps\api\.venv is missing - run without --no-install, or run uv sync in apps\api.
goto :fail

:err_no_node_modules
echo [FAIL] apps\web\node_modules is missing - run without --no-install, or run pnpm install in apps\web.
goto :fail

:err_ports
echo [FAIL] Ports 3000 and 4000 are not free - see the messages above.
goto :fail

:err_db
echo [FAIL] PostgreSQL did not start or did not become healthy within 90 seconds.
echo        Details: docker compose logs db
echo        If port !POSTGRES_HOST_PORT! is taken, set POSTGRES_HOST_PORT and the port in DATABASE_URL in .env.
goto :fail

:err_migrate
echo [FAIL] Migrations failed - fix the error above and run start.bat again.
echo        PostgreSQL keeps running; stop.bat stops it.
goto :fail

:err_seed
echo [FAIL] The seed script failed - see the error above.
goto :fail

:err_api_timeout
call :show_log api
echo [FAIL] The API did not answer http://localhost:4000/health within about 90 seconds.
goto :fail_stop

:err_web_timeout
call :show_log web
echo [FAIL] The web app did not answer http://localhost:3000 in time.
goto :fail_stop

:fail_stop
echo [....] Stopping what start.bat started
call "%ROOT%\stop.bat" --quiet

:fail
echo.
echo BayFlow did not start. Fix the problem above, then run start.bat again.
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 1
