@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "OPENAI_BASE_URL=http://localhost:20128/v1"
set "OPENAI_API_KEY=sk-5e22593ab0b2f60a-f74aef-bc3cb715"
set "OPENAI_MODEL=cgpt-web/o3"

set "CODEX_HOME=%USERPROFILE%\.codex-omniroute"
set "API_TIMEOUT_MS=600000"

if not exist "%CODEX_HOME%" mkdir "%CODEX_HOME%"

(
echo model = "%OPENAI_MODEL%"
echo model_provider = "omniroute"
echo.
echo [model_providers.omniroute]
echo name = "OmniRoute"
echo base_url = "%OPENAI_BASE_URL%"
echo env_key = "OPENAI_API_KEY"
echo wire_api = "responses"
) > "%CODEX_HOME%\config.toml"

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found.
  exit /b 1
)

where codex >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Codex CLI not found.
  echo Install with:
  echo npm install -g @openai/codex
  exit /b 1
)

echo.
echo Starting ChatGPT Web via OmniRoute
echo BASE URL: %OPENAI_BASE_URL%
echo MODEL:    %OPENAI_MODEL%
echo CODEX_HOME: %CODEX_HOME%
echo.

call codex --model "%OPENAI_MODEL%" %*

exit /b %ERRORLEVEL%