param(
    [ValidateSet('electronic', 'print')]
    [string]$Mode = 'electronic'
)

$ErrorActionPreference = 'Stop'
$sourceFile = if ($Mode -eq 'print') { 'main-print.tex' } else { 'main.tex' }
$jobName = [System.IO.Path]::GetFileNameWithoutExtension($sourceFile)

Push-Location $PSScriptRoot
try {
    foreach ($commandName in @('xelatex')) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
            throw "$commandName was not found. Install MiKTeX or TeX Live first."
        }
    }

    & xelatex --disable-installer -interaction=nonstopmode -halt-on-error -file-line-error $sourceFile
    if ($LASTEXITCODE -ne 0) { throw 'The first XeLaTeX pass failed.' }

    & xelatex --disable-installer -interaction=nonstopmode -halt-on-error -file-line-error $sourceFile
    if ($LASTEXITCODE -ne 0) { throw 'The second XeLaTeX pass failed.' }

    Write-Host "Build complete: $jobName.pdf"
}
finally {
    Pop-Location
}
