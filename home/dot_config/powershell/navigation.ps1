function cdl {
    param([Parameter(Mandatory, Position=0)][string]$Path)
    Set-Location -LiteralPath $Path
}

# Track all location changes, including cd and zoxide. PowerShell's built-in
# cd - re-expands wildcard characters in the previous path; use a literal path.
if ($PSVersionTable.PSVersion.Major -ge 7 -and -not $global:DotfilesLocationHookInitialized) {
    $global:DotfilesOriginalLocationAction = $ExecutionContext.InvokeCommand.LocationChangedAction
    $ExecutionContext.InvokeCommand.LocationChangedAction = {
        param($Sender, $EventArgs)
        if ($EventArgs.OldPath.Path -cne $EventArgs.NewPath.Path) {
            $global:DotfilesPreviousLocation = $EventArgs.OldPath.Path
        }
        if ($global:DotfilesOriginalLocationAction) {
            $global:DotfilesOriginalLocationAction.Invoke($Sender, $EventArgs)
        }
    }
    $global:DotfilesLocationHookInitialized = $true
}
function - {
    if (-not $global:DotfilesPreviousLocation) { throw 'No previous directory is available in this session.' }
    Set-Location -LiteralPath $global:DotfilesPreviousLocation
}

function lf {
    $temporaryPath = [IO.Path]::GetTempFileName()
    try {
        & lf.exe "-last-dir-path=$temporaryPath" @args
        $directory = Get-Content -LiteralPath $temporaryPath -Raw -Encoding UTF8
        if ($directory) { $directory = $directory.TrimEnd("`r", "`n") }
        if ($directory -and (Test-Path -LiteralPath $directory -PathType Container)) {
            Set-Location -LiteralPath $directory
        }
    } finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}

# Pure helper for the Enter binding. Never evaluate expressions or override an
# existing command name when recognizing a literal directory.
function Get-DotfilesAutoCdPath {
    param([string]$Line)
    $candidate = $Line.Trim()
    if (-not $candidate -or (Get-Command $candidate -ErrorAction SilentlyContinue)) { return }
    if ($candidate.Length -ge 2 -and $candidate.StartsWith("'") -and $candidate.EndsWith("'")) {
        $candidate = $candidate.Substring(1, $candidate.Length - 2).Replace("''", "'")
    } elseif ($candidate.Length -ge 2 -and $candidate.StartsWith('"') -and $candidate.EndsWith('"')) {
        $candidate = $candidate.Substring(1, $candidate.Length - 2)
    }
    if ($candidate -eq '~') { $candidate = $HOME }
    elseif ($candidate -match '^~[/\\]') { $candidate = Join-Path $HOME $candidate.Substring(2) }
    if (Test-Path -LiteralPath $candidate -PathType Container -ErrorAction SilentlyContinue) {
        (Get-Item -LiteralPath $candidate).FullName
    }
}
