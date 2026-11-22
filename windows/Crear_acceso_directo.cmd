@echo off
setlocal
set "ANALIZADOR_DIR=%~dp0"
powershell.exe -NoProfile -Command "$dir=$env:ANALIZADOR_DIR; $exe=Join-Path $dir 'AnalizadorImpedanciasLC.exe'; $icono=$exe; if (!(Test-Path -LiteralPath $exe)) { $dir=Split-Path -Parent $dir.TrimEnd('\'); $exe=Join-Path $dir 'iniciar.bat'; $icono=Join-Path $dir 'recursos\utn-fondo-blanco.ico' }; if (!(Test-Path -LiteralPath $exe)) { throw 'No se encontro el programa junto al acceso directo.' }; $shell=New-Object -ComObject WScript.Shell; $link=$shell.CreateShortcut((Join-Path $shell.SpecialFolders.Item('Desktop') 'Analizador de Impedancias LC Complejas.lnk')); $link.TargetPath=$exe; $link.WorkingDirectory=$dir; $link.IconLocation=$icono+',0'; $link.Description='Analizador de Impedancias LC Complejas'; $link.Save(); Write-Host 'Acceso directo creado en el escritorio.'"
if errorlevel 1 (
    pause
    exit /b 1
)
