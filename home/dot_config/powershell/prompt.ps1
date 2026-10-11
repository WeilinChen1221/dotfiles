if ($global:DotfilesPromptInitialized) { return }
function Invoke-Starship-PreCommand {
    if ($global:DotfilesFnmInitialized -and
        ((Test-Path -LiteralPath '.nvmrc') -or (Test-Path -LiteralPath '.node-version') -or
         (Test-Path -LiteralPath 'package.json'))) {
        & fnm.exe use --silent-if-unchanged
    }
}
if (Get-Command starship.exe -CommandType Application -ErrorAction SilentlyContinue) {
    starship.exe init powershell | Out-String | Invoke-Expression
}
# zoxide wraps the current prompt. Initialize it after Starship.
if (Get-Command zoxide.exe -CommandType Application -ErrorAction SilentlyContinue) {
    zoxide.exe init powershell | Out-String | Invoke-Expression
}
$global:DotfilesPromptInitialized = $true
