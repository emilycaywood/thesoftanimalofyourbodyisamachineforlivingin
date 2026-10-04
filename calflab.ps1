# CALFLAB bootstrap launcher (PowerShell 5.1+).
#   .\calflab.ps1 setup | doctor | lab | test | demo <name> | new-plugin <type> <name>
# Keeps the virtualenv outside the repo (see DECISIONS.md ADR-003) and runs the
# Typer CLI through uv.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $env:CALFLAB_HOME) { $env:CALFLAB_HOME = Join-Path $env:LOCALAPPDATA 'calflab' }
$env:CALFLAB_REPO = $repo
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:CALFLAB_HOME 'venv'
$env:UV_LINK_MODE = 'copy'
# Keep bytecode caches off the (possibly cloud-synced) repo drive.
$env:PYTHONPYCACHEPREFIX = Join-Path $env:CALFLAB_HOME 'pycache'
$env:PYTHONUTF8 = '1'

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) { $uvCmd = @($uv.Source) }
else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $py) { Write-Error 'Neither uv nor python found. Install uv: https://docs.astral.sh/uv/'; exit 1 }
    & $py.Source -m uv --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing uv (python -m pip install --user uv)...'
        & $py.Source -m pip install --user --quiet uv
    }
    $uvCmd = @($py.Source, '-m', 'uv')
}

$exe = $uvCmd[0]
$pre = @()
if ($uvCmd.Count -gt 1) { $pre = $uvCmd[1..($uvCmd.Count - 1)] }
# Native tools write progress to stderr; that must not abort the script (PowerShell 5.1).
$ErrorActionPreference = 'Continue'
& $exe @pre run --project $repo --all-extras calflab @args
exit $LASTEXITCODE
