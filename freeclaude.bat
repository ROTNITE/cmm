@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM ============================================================
REM Claude Code via OmniRoute
REM Edit OMNIROUTE_HOST and OMNIROUTE_KEY below, then run:
REM   cc-omniroute.bat
REM   cc-omniroute.bat "say hello"
REM ============================================================

REM For local OmniRoute use root URL WITHOUT /v1 for Claude Code.
set "OMNIROUTE_HOST=http://localhost:20128/v1"

REM Paste your OmniRoute API key from Dashboard -> API Manager.
set "OMNIROUTE_KEY=sk-5e22593ab0b2f60a-f74aef-bc3cb715"

REM Prevent a real Anthropic key from taking priority in this session.
set "ANTHROPIC_API_KEY="

REM Claude Code gateway variables.
set "ANTHROPIC_BASE_URL=%OMNIROUTE_HOST%"
set "ANTHROPIC_AUTH_TOKEN=%OMNIROUTE_KEY%"

REM Model for Claude Code through OmniRoute.
set "ANTHROPIC_MODEL=kr/claude-sonnet-4.5"
set "ANTHROPIC_CUSTOM_MODEL_OPTION=kr/claude-sonnet-4.5"

REM Optional: increase timeout when routing through a gateway.
set "API_TIMEOUT_MS=600000"

call claude --model "%ANTHROPIC_MODEL%" --permission-mode bypassPermissions %*

REM Optional troubleshooting:
REM If your gateway rejects Anthropic beta headers, uncomment:
REM set "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1"
REM If you want less telemetry/nonessential network traffic, uncomment:
REM set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"

if "%OMNIROUTE_KEY%"=="sk-your-omniroute-key" (
  echo [ERROR] Edit this file and replace OMNIROUTE_KEY with your OmniRoute API key.
  echo         Get it from: http://localhost:20128/dashboard/api-manager
  exit /b 1
)

where claude >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Claude Code CLI was not found in PATH.
  echo         Install it with:
  echo         npm install -g @anthropic-ai/claude-code
  exit /b 1
)

echo Starting Claude Code via OmniRoute:
echo   ANTHROPIC_BASE_URL=%ANTHROPIC_BASE_URL%
echo   API key: [hidden]
echo.

call claude %*
set "EXITCODE=%ERRORLEVEL%"

echo.
echo Claude Code exited with code %EXITCODE%.
exit /b %EXITCODE%
