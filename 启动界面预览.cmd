@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 goto missing_python

python -c "import PySide6, websockets, yt_dlp, segno, PIL" >nul 2>&1
if errorlevel 1 goto missing_dependencies

python -c "from app.runtime import configure_runtime; configure_runtime(); import mpv"
if errorlevel 1 goto missing_runtime

python "%~dp0client.py" %*
set "CLIENT_EXIT_CODE=%ERRORLEVEL%"
if "%CLIENT_EXIT_CODE%"=="0" exit /b 0
echo.
echo 客户端启动或运行失败，请根据上方错误信息检查 Python 环境。
pause
exit /b %CLIENT_EXIT_CODE%

:missing_python
echo 未找到可用的系统 Python 3.8 或更高版本，请手动配置 Python 环境。
echo 安装 Python 并将其加入 PATH，然后重新运行此脚本。
echo 可在终端运行 python --version 检查配置。
pause
exit /b 1

:missing_dependencies
echo 系统 Python 缺少项目依赖，请手动配置 Python 环境。
echo 请在本目录执行以下命令，然后重新运行此脚本：
echo   python -m pip install -r requirements.txt
pause
exit /b 1

:missing_runtime
echo Qt 或 mpv 运行库加载失败，请根据上方错误信息手动配置运行环境。
echo 请确认已安装项目依赖，并将实际 DLL 放到 libmpv\libmpv-2.dll。
echo Python 与 DLL 的架构必须一致。
pause
exit /b 1
