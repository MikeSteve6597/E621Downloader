@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   E6Dler 一键打包
echo ==========================================
echo.

echo [1/2] 安装依赖...
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo.
echo [2/2] 开始打包...
python -m PyInstaller --noconfirm --clean E6dl.spec
if errorlevel 1 goto :error

echo.
echo 打包完成：dist\E6dl.exe
pause
exit /b 0

:error
echo.
echo 构建失败，请检查上方错误信息。
pause
exit /b 1
