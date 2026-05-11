@echo off
chcp 65001 >nul 2>&1
title AI Document Review - 一键启动

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║        🚀 AI Document Review - 一键启动                  ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo 📁 项目目录: %CD%
echo.

:: 检查 Node.js
echo 🔍 检查 Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js 未安装，请先安装 Node.js
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do echo ✅ Node.js: %%i

:: 检查 Python
echo 🔍 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装，请先安装 Python
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo ✅ Python: %%i

echo.

:: 检查环境变量文件
if not exist "app\api\.env" (
    echo ⚠️  未找到 app\api\.env 文件
    echo    请复制 app\api\.env.tpl 并重命名为 .env，然后配置 API Key
    echo.
)

:: 启动后端
echo 🔧 启动后端服务 (FastAPI)...
start "Backend - FastAPI" cmd /k "cd /d %~dp0app\api && if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo    ✅ 后端服务已在新窗口启动
echo    📍 API 地址: http://localhost:8000
echo    📍 API 文档: http://localhost:8000/docs
echo.

:: 等待后端启动
echo ⏳ 等待后端服务启动 (5秒)...
timeout /t 5 /nobreak >nul

:: 启动前端
echo 🎨 启动前端服务 (Vite)...
start "Frontend - Vite" cmd /k "cd /d %~dp0app\ui && npm run dev"
echo    ✅ 前端服务已在新窗口启动
echo    📍 前端地址: http://localhost:5173
echo.

:: 完成
echo ═══════════════════════════════════════════════════════════
echo 🎉 所有服务已启动！
echo.
echo 📌 服务地址:
echo    • 前端 UI:  http://localhost:5173
echo    • 后端 API: http://localhost:8000
echo    • API 文档: http://localhost:8000/docs
echo.
echo 📌 关闭服务:
echo    • 关闭各自的命令行窗口即可停止服务
echo ═══════════════════════════════════════════════════════════
echo.

:: 询问是否打开浏览器
set /p openBrowser="是否打开浏览器？(Y/n): "
if /i not "%openBrowser%"=="n" (
    start http://localhost:5173
)

echo.
echo 按任意键关闭此窗口（服务会继续运行）...
pause >nul

