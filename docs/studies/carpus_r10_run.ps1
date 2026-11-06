# Session R10 (ADR-101): run carpus_r10.py stages for a filtered set of bodies (labels containing -Match).
# .\docs\studies\carpus_r10_run.ps1 -Stage grid -Match "new shoulders"
param([string]$Stage = "grid", [string]$Match = "", [string]$Extra = "")
$py = "$env:LOCALAPPDATA\calflab\venv\Scripts\python.exe"
$names = & $py -c "import sys; sys.path.insert(0, 'docs/studies'); from carpus_r10 import cases; print(';'.join(c for l, c in cases().items() if '$Match' in l))"
$args2 = @("docs\studies\carpus_r10.py", "projects\robot-calf-final", $Stage, "--cases=$names", "--workers=6")
if ($Extra) { $args2 += $Extra }
& $py @args2
