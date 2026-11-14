function Invoke-Starship-PreCommand {
    # A mode redraw must not run command hooks or reset the cursor.
    if ($global:DotfilesViModeRedraw) { return }
    if ($Host.UI.SupportsVirtualTerminal -and -not [Console]::IsOutputRedirected) {
        Set-DotfilesViCursor Insert
    }
    if ($global:DotfilesFnmInitialized -and
        ((Test-Path -LiteralPath '.nvmrc') -or (Test-Path -LiteralPath '.node-version') -or
         (Test-Path -LiteralPath 'package.json'))) {
        & fnm.exe use --silent-if-unchanged
    }
    # psmux disables predictions after profiles load. Restore only once so
    # subsequent prompts respect the user's Ctrl+\ toggle.
    if (-not $global:DotfilesPredictionInitialized -and
        (Get-Command Set-PSReadLineOption -ErrorAction SilentlyContinue)) {
        if ((Get-Command Set-PSReadLineOption).Parameters.ContainsKey('PredictionSource') -and
            $Host.UI.SupportsVirtualTerminal -and -not [Console]::IsOutputRedirected) {
            Set-PSReadLineOption -PredictionSource History -PredictionViewStyle InlineView
        }
        $global:DotfilesPredictionInitialized = $true
    }
}
if (-not $global:DotfilesPromptInitialized) {
    if (Get-Command starship.exe -CommandType Application -ErrorAction SilentlyContinue) {
        starship.exe init powershell | Out-String | Invoke-Expression
    }
    # zoxide wraps the current prompt. Initialize it after Starship.
    if (Get-Command zoxide.exe -CommandType Application -ErrorAction SilentlyContinue) {
        zoxide.exe init powershell | Out-String | Invoke-Expression
    }
    $global:DotfilesPromptInitialized = $true
}

# Install after Starship so one handler updates both the arrow and cursor.
$readlineParameters = (Get-Command Set-PSReadLineOption).Parameters
if ($readlineParameters.ContainsKey('ViModeChangeHandler')) {
    Set-PSReadLineOption -ViModeIndicator Script -ViModeChangeHandler {
        param($Mode)
        $global:DotfilesViModeRedraw = $true
        try {
            [Microsoft.PowerShell.PSConsoleReadLine]::InvokePrompt()
        } finally {
            $global:DotfilesViModeRedraw = $false
            Set-DotfilesViCursor $Mode
        }
    }
} else {
    Set-PSReadLineOption -ViModeIndicator Cursor
}
