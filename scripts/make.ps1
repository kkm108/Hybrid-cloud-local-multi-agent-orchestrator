<#
.SYNOPSIS
    Windows parity runner for SocialAI §13 targets (T16).

.DESCRIPTION
    Mirrors the repo Makefile targets (test, lint, smoke, backup, consult,
    restore BUNDLE=<zip>) with faithful child exit codes. --dry-run prints the
    resolved command without executing it. A make.cmd shim forwards all args.

    Tokens are parsed as raw arguments so `powershell -File make.ps1
    --dry-run test` binds as expected under -File (named switches are not
    bound for -File scripts).
#>
[CmdletBinding(PositionalBinding = $true)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RawArgs
)

$ErrorActionPreference = "Stop"

$Targets = [ordered]@{ }
$Targets["test"]    = 'python -m pytest -q -m "not gpu and not live and not ui"'
$Targets["lint"]    = 'python -m ruff check .'
$Targets["smoke"]   = 'python -m socialai.cli --smoke'
$Targets["backup"]  = 'python scripts/backup.py --mode restore'
$Targets["consult"] = 'python scripts/backup.py --mode consult'
$Targets["restore"] = 'python scripts/restore.py --bundle {BUNDLE}'

# Parse raw tokens: bare target plus optional flags --
#   --dry-run | -dry-run : print resolved command, do not execute
#   --BUNDLE <zip>       : bundle path (restore)
#   BUNDLE=<zip>         : make-style bundle path (restore)
$Target = ""
$BUNDLE = ""
$DryRun = $false
$bundleNext = $false
foreach ($arg in $RawArgs) {
    if ($bundleNext) {
        $BUNDLE = $arg
        $bundleNext = $false
        continue
    }
    if ($arg -eq "--dry-run" -or $arg -eq "-dry-run") { $DryRun = $true; continue }
    if ($arg -eq "--BUNDLE" -or $arg -eq "-BUNDLE") { $bundleNext = $true; continue }
    if ($arg -like "BUNDLE=*") { $BUNDLE = $arg.Substring(7); continue }
    if ($Target -eq "") { $Target = $arg }
}

function Write-Usage {
    "USAGE: make.ps1 <test|lint|smoke|backup|consult|restore> [--BUNDLE <zip>] [--dry-run]"
}

if ([string]::IsNullOrWhiteSpace($Target)) {
    Write-Usage
    exit 2
}
if (-not $Targets.Contains($Target)) {
    Write-Usage
    "UNKNOWN TARGET: $Target"
    exit 2
}

$command = $Targets[$Target]
if ($Target -eq "restore") {
    if ([string]::IsNullOrWhiteSpace($BUNDLE)) {
        "restore requires BUNDLE=<zip> (--BUNDLE <zip>)"
        exit 2
    }
    $command = $command -replace "\{BUNDLE\}", $BUNDLE
}

"> $command"
if ($DryRun) {
    exit 0
}

cmd /c $command
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 1 }
exit $code