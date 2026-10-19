# Build with the free compiler supplied by the Windows .NET Framework.
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
$compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compilerPath)) { throw 'The Windows .NET Framework compiler is unavailable.' }
& $compilerPath /nologo /target:winexe /reference:System.Windows.Forms.dll "/out:$appRoot\OpenCal.exe" "$PSScriptRoot\Launcher.cs"
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
