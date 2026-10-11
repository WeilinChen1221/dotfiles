# Dot-source modules into the caller's scope so functions and aliases persist.
. (Join-Path $PSScriptRoot 'environment.ps1')
. (Join-Path $PSScriptRoot 'aliases.ps1')
. (Join-Path $PSScriptRoot 'navigation.ps1')

# SSH commands and redirected hosts must not initialize a console line editor.
$dotfilesInteractive = $Host.Name -eq 'ConsoleHost' -and
    -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected -and
    -not ([Environment]::GetCommandLineArgs() -match '^-(NonInteractive|Command|EncodedCommand|File|c|ec|f)$')
if ($dotfilesInteractive) {
    . (Join-Path $PSScriptRoot 'completion.ps1')
    . (Join-Path $PSScriptRoot 'fzf.ps1')
    . (Join-Path $PSScriptRoot 'bindings.ps1')
    . (Join-Path $PSScriptRoot 'prompt.ps1')
}
