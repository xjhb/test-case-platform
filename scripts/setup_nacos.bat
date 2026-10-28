@echo off
chcp 65001 >nul
echo ============================================
echo   Nacos 安装助手 (Windows)
echo ============================================
echo.

REM 检查 Java
java -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Java，请先安装 JDK 8+
    echo 下载地址: https://adoptium.net/
    echo.
    pause
    exit /b 1
)

echo [OK] Java 已安装
echo.

REM 检查是否已下载
if exist "%~dp0..\nacos\bin\startup.cmd" (
    echo [OK] Nacos 已存在
    goto :start_nacos
)

REM 下载 Nacos
set NACOS_VERSION=2.4.3
set NACOS_URL=https://github.com/alibaba/nacos/releases/download/%NACOS_VERSION%/nacos-server-%NACOS_VERSION%.zip
set DOWNLOAD_PATH=%~dp0..\nacos-server-%NACOS_VERSION%.zip

echo [下载] 正在下载 Nacos %NACOS_VERSION% ...
echo 地址: %NACOS_URL%
echo.

powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%NACOS_URL%' -OutFile '%DOWNLOAD_PATH%' -UseBasicParsing }"

if %errorlevel% neq 0 (
    echo [错误] 下载失败，请手动下载
    echo 访问: https://github.com/alibaba/nacos/releases
    pause
    exit /b 1
)

echo [解压] 正在解压...
powershell -Command "& { Expand-Archive -Path '%DOWNLOAD_PATH%' -DestinationPath '%~dp0..\nacos-temp' -Force }"

REM 移动文件
if exist "%~dp0..\nacos-temp\nacos" (
    move "%~dp0..\nacos-temp\nacos" "%~dp0..\nacos" >nul
    rmdir /s /q "%~dp0..\nacos-temp" >nul 2>&1
) else (
    move "%~dp0..\nacos-temp" "%~dp0..\nacos" >nul 2>&1
)

del "%DOWNLOAD_PATH%" >nul 2>&1

echo [OK] Nacos 已安装到: %~dp0..\nacos
echo.

:start_nacos
echo ============================================
echo   启动 Nacos (单机模式)
echo ============================================
echo.
echo 控制台地址: http://localhost:8848/nacos
echo 默认账号: nacos / nacos
echo.
echo 按 Ctrl+C 停止 Nacos
echo.

cd /d "%~dp0..\nacos\bin"
call startup.cmd -m standalone
