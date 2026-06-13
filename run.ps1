# tieout runner for PowerShell.
# Sets PYTHONPATH, loads ANTHROPIC_API_KEY from the out-of-repo credentials file
# (only needed for UNCACHED LLM calls), then runs whatever you pass.
#
#   .\run.ps1 scripts\demo.py            # combined report -> out\report.md
#   .\run.ps1 scripts\phase0_real.py COST
#   .\run.ps1 -m pytest                  # run the test suite
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

$cred = Join-Path $env:LOCALAPPDATA "tieout\credentials.env"
if (Test-Path $cred) {
    Get-Content $cred | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
        }
    }
}

python @args
