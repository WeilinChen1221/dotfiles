# Dot-source modules into the caller's scope so functions and aliases persist.
. (Join-Path $PSScriptRoot 'environment.ps1')
. (Join-Path $PSScriptRoot 'aliases.ps1')
. (Join-Path $PSScriptRoot 'navigation.ps1')

# SSH commands and redirected hosts must not initialize a console line editor.
# psmux launches with -NoExit -Command; keep its line editor enabled.
$cmdArgs = [Environment]::GetCommandLineArgs()
$isNonInteractive = [bool]($cmdArgs -match '^-(NonInteractive|noni)$')
$isBatch = [bool]($cmdArgs -match '^-(Command|EncodedCommand|File|c|ec|f)$')
$hasNoExit = [bool]($cmdArgs -match '^-(NoExit|noe)$') -or [bool]$env:TMUX

$dotfilesInteractive = $Host.Name -eq 'ConsoleHost' -and
    -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected -and
    (-not $isNonInteractive) -and (-not $isBatch -or $hasNoExit)
if ($dotfilesInteractive) {
    . (Join-Path $PSScriptRoot 'completion.ps1')
    . (Join-Path $PSScriptRoot 'fzf.ps1')
    . (Join-Path $PSScriptRoot 'bindings.ps1')
    . (Join-Path $PSScriptRoot 'prompt.ps1')
}
