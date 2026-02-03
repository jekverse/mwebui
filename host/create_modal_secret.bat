@echo off
REM Windows batch script to create Modal secrets from .env file

echo === Loading .env file ===
echo.

REM Load .env file (simple version - doesn't handle complex values)
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    set "%%a=%%b"
    echo Loaded: %%a
)

echo.
echo === Deploying Modal Secrets ===
echo.

REM Delete old secret (ignore errors)
echo Removing old secrets (if any)...
modal secret delete my-secrets --yes >nul 2>&1

REM Create new secret
echo Creating new secret 'my-secrets'...

modal secret create my-secrets ^
    GH_TOKEN="%GH_TOKEN%" ^
    HF_TOKEN="%HF_TOKEN%" ^
    CLOUDFLARED_TOKEN="%CLOUDFLARED_TOKEN%" ^
    SSH_KEY="%SSH_KEY%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✓ Secrets deployed successfully!
    echo.
    echo Verify with: modal secret list
    echo.
) else (
    echo.
    echo × Failed to deploy secrets
    echo.
    exit /b 1
)
