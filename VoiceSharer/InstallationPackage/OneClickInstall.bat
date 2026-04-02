@echo off
chcp 65001 > nul
echo ========================================================
echo       Multi-Device Audio Control Installation
echo ========================================================
echo.

echo [1/3] Checking environment...

:: Check for VB-Cable
if exist "VB-Audio_Driver\VBCABLE_Driver_Pack45\VBCABLE_Setup_x64.exe" (
    echo [2/3] Installing VB-Audio Virtual Cable Driver...
    echo       Please allow administrator privileges if requested.
    echo       IMPORTANT: You may need to restart your computer after this.
    start /wait "" "VB-Audio_Driver\VBCABLE_Driver_Pack45\VBCABLE_Setup_x64.exe"
) else (
    echo [2/3] VB-Audio driver installer not found in expected path.
    echo       Expected: VB-Audio_Driver\VBCABLE_Driver_Pack45\VBCABLE_Setup_x64.exe
    echo       Skipping driver installation.
    echo       If you haven't installed VB-Cable, please download and install it manually.
)

echo.
echo [3/3] Setting up application...

:: Create directory in Local AppData
set "INSTALL_DIR=%LOCALAPPDATA%\MultiDeviceAudioControl"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Copy executable
copy /Y "MultiDeviceAudioControl.exe" "%INSTALL_DIR%\"

:: Create Shortcut (using PowerShell)
echo       Creating shortcut on Desktop...
set "SHORTCUT_SCRIPT=%temp%\CreateShortcut.ps1"
echo $s=(New-Object -COM WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\MultiDeviceAudioControl.lnk') > "%SHORTCUT_SCRIPT%"
echo $s.TargetPath='%INSTALL_DIR%\MultiDeviceAudioControl.exe' >> "%SHORTCUT_SCRIPT%"
echo $s.WorkingDirectory='%INSTALL_DIR%' >> "%SHORTCUT_SCRIPT%"
echo $s.Save() >> "%SHORTCUT_SCRIPT%"

powershell -ExecutionPolicy Bypass -File "%SHORTCUT_SCRIPT%"
del "%SHORTCUT_SCRIPT%"

echo.
echo ========================================================
echo       Installation Complete!
echo ========================================================
echo You can now start the application from your Desktop.
echo.
pause