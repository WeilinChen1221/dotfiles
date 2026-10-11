foreach ($entry in @{
    XDG_CONFIG_HOME = '.config'
    XDG_CACHE_HOME = '.cache'
    XDG_DATA_HOME = '.local/share'
    XDG_STATE_HOME = '.local/state'
}.GetEnumerator()) {
    if (-not [Environment]::GetEnvironmentVariable($entry.Key, 'Process')) {
        [Environment]::SetEnvironmentVariable($entry.Key, (Join-Path $HOME $entry.Value), 'Process')
    }
}

$personalBin = Join-Path $HOME '.local/bin'
$env:PATH = (@($personalBin) + @($env:PATH -split [IO.Path]::PathSeparator |
    Where-Object { $_ -and $_.TrimEnd('\', '/') -ne $personalBin.TrimEnd('\', '/') } |
    Select-Object -Unique)) -join [IO.Path]::PathSeparator
$env:STARSHIP_CONFIG = Join-Path $env:XDG_CONFIG_HOME 'starship.toml'
$env:VIRTUAL_ENV_DISABLE_PROMPT = '1'

# Preserve this Windows machine's existing proxy and editor.
$env:HTTP_PROXY = 'http://127.0.0.1:10808'
$env:HTTPS_PROXY = $env:HTTP_PROXY
Set-Alias -Name notepad -Value notepad3
$env:VISUAL = 'notepad'
$env:EDITOR = 'notepad'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$global:OutputEncoding = [Text.UTF8Encoding]::new($false)

$iconPath = Join-Path $env:XDG_CONFIG_HOME 'lf/icons'
if (Test-Path -LiteralPath $iconPath) {
    $env:LF_ICONS = (Get-Content -LiteralPath $iconPath -Encoding UTF8) -join ':'
}

if (-not $global:DotfilesFnmInitialized -and
    (Get-Command fnm.exe -CommandType Application -ErrorAction SilentlyContinue)) {
    # The prompt checks version files after any navigation command. fnm's
    # --use-on-cd wrapper would only intercept cd, missing cdl, lf, and zoxide.
    fnm.exe env --shell powershell | Out-String | Invoke-Expression
    $global:DotfilesFnmInitialized = $true
}
