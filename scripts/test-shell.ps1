#Requires -Version 7.4
param([string]$ConfigurationPath = (Join-Path $HOME '.config/powershell'))
$ErrorActionPreference = 'Stop'
function Assert-Shell {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

# Parse every rendered module before executing it.
foreach ($file in Get-ChildItem -LiteralPath $ConfigurationPath -Filter '*.ps1') {
    $tokens = $null
    $parseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors)
    Assert-Shell ($parseErrors.Count -eq 0) "Parse error in $($file.Name): $parseErrors"
}
. (Join-Path $ConfigurationPath 'profile.ps1')
# Exercise interactive initialization without needing a real terminal here.
foreach ($module in 'completion', 'fzf', 'bindings', 'prompt') {
    . (Join-Path $ConfigurationPath "$module.ps1")
}
Assert-Shell ((Get-PSReadLineOption).EditMode -eq 'Vi') 'Vi editing is not enabled'
if ($Host.UI.SupportsVirtualTerminal -and -not [Console]::IsOutputRedirected) {
    Assert-Shell ((Get-PSReadLineOption).PredictionSource -eq 'History') 'History predictions are not enabled'
}
$keys = Get-PSReadLineKeyHandler -Bound
foreach ($description in 'FzfHistory', 'FzfFiles', 'FindVisibleFile', 'AutoCd', 'SubstringHistoryUp', 'ToggleSuggestions') {
    # Vi command-mode chords appear in angle brackets; insert chords do not.
    Assert-Shell (@($keys | Where-Object Function -eq $description).Count -eq 2) "Missing $description binding in one of the Vi keymaps"
}
$handler = (Get-PSReadLineOption).AddToHistoryHandler
Assert-Shell ($handler.Invoke(' echo private') -eq $false) 'Leading-space commands entered history'
Assert-Shell ([bool]$handler.Invoke('echo hello')) 'Ordinary commands are excluded from history'
$beforeHandler = $global:DotfilesOriginalHistoryHandler
. (Join-Path $ConfigurationPath 'completion.ps1')
Assert-Shell ([object]::ReferenceEquals($beforeHandler, $global:DotfilesOriginalHistoryHandler)) 'Re-sourcing recursively wrapped the history filter'
. (Join-Path $ConfigurationPath 'fzf.ps1')
. (Join-Path $ConfigurationPath 'bindings.ps1')
Assert-Shell (@(($env:PATH -split ';') | Where-Object { $_ -eq (Join-Path $HOME '.local/bin') }).Count -eq 1) 'Personal PATH contains duplicates'
Assert-Shell ($env:EDITOR -eq 'notepad') 'Windows editor changed'
Assert-Shell (-not (Get-Command vim -CommandType Function -ErrorAction SilentlyContinue)) 'Neovim alias was ported'

$temporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) ('dotfiles-shell-test-' + [guid]::NewGuid())
$originalLocation = Get-Location
$previousPager = $env:PAGER
$previousGitPager = $env:GIT_PAGER
$previousStarshipLog = $env:STARSHIP_LOG
try {
    [void][IO.Directory]::CreateDirectory($temporaryDirectory)
    # This name catches wildcard expansion, quoting errors, and UTF-8 mistakes.
    $name = "中文 [test] O'Brien `$file.txt"
    $path = Join-Path $temporaryDirectory $name
    [IO.File]::WriteAllText($path, "hello 中文`n", [Text.UTF8Encoding]::new($false))
    $token = ConvertTo-DotfilesPathToken $path
    $actual = & ([scriptblock]::Create('Get-Item -LiteralPath ' + $token))
    Assert-Shell ($actual.FullName -eq $path) 'Selected file token does not round-trip'
    $content = (cat --paging=never --color=never --style=plain $path | Out-String).Trim()
    Assert-Shell ($content -eq 'hello 中文') 'bat wrapper lost file content or UTF-8'
    Assert-Shell (('hello 中文' | grep hello --no-heading --color=never | Out-String).Trim() -eq 'hello 中文') 'Pipeline input was lost by grep wrapper'
    $listing = ll --color=never $temporaryDirectory | Out-String
    Assert-Shell ($listing.Contains($name)) 'eza wrapper lost a literal filename'
    cdl $temporaryDirectory
    $found = & fd.exe --type f --strip-cwd-prefix | & fzf.exe --filter "O'Brien"
    Assert-Shell ($LASTEXITCODE -eq 0 -and [bool]$found) 'fd/fzf failed to find a quoted filename'
    $preview = & bat.exe --paging=never --color=never --style=plain,numbers --line-range=:500 $path | Out-String
    Assert-Shell ($preview.Contains('中文')) 'bat preview lost UTF-8'

    $specialDirectory = Join-Path $temporaryDirectory "dir [x] O'Brien 中文"
    [void][IO.Directory]::CreateDirectory($specialDirectory)
    Assert-Shell ((Get-DotfilesAutoCdPath (ConvertTo-DotfilesPathToken $specialDirectory)) -eq $specialDirectory) 'AUTOCD lost a literal directory'
    Assert-Shell (-not (Get-DotfilesAutoCdPath 'Write-Output hello')) 'AUTOCD intercepted a command'
    cdl $specialDirectory
    Assert-Shell ((Get-Location).Path -eq $specialDirectory) 'cdl expanded bracket wildcards'
    cdl $temporaryDirectory
    & '-'
    Assert-Shell ((Get-Location).Path -eq $specialDirectory) 'Previous-directory navigation failed'

    $matches = @(Get-DotfilesHistoryMatches @('git status', 'echo [x]', 'git log', 'git status') 'git')
    Assert-Shell (($matches -join '|') -eq 'git status|git log') 'Substring history order/deduplication failed'
    Assert-Shell (@(Get-DotfilesHistoryMatches @('echo [x]', 'echo x') '[x]').Count -eq 1) 'History search treated the query as a wildcard'
    Assert-Shell ((@(Get-DotfilesHistoryMatches @('first', 'second') '') -join '|') -eq 'second|first') 'Empty-query history browsing failed'

    # Replace only the executable in this process to check lf navigation and
    # cleanup, including an empty last-directory file on cancellation.
    $global:DotfilesTestDirectory = $specialDirectory
    $global:DotfilesTestLastPath = $null
    function global:lf.exe {
        $global:DotfilesTestLastPath = $args[0].Substring('-last-dir-path='.Length)
        [IO.File]::WriteAllText($global:DotfilesTestLastPath, $global:DotfilesTestDirectory)
    }
    cdl $temporaryDirectory
    lf
    Assert-Shell ((Get-Location).Path -eq $specialDirectory) 'lf did not follow its last directory'
    Assert-Shell (-not (Test-Path -LiteralPath $global:DotfilesTestLastPath)) 'lf left its temporary file behind'
    $global:DotfilesTestDirectory = ''
    lf
    Assert-Shell (-not (Test-Path -LiteralPath $global:DotfilesTestLastPath)) 'lf cancellation left its temporary file behind'

    $env:PAGER = 'original pager'
    $env:GIT_PAGER = 'original git pager'
    cdl (Join-Path $HOME '.local/share/chezmoi')
    glog -1 --format=%h | Out-Null
    Assert-Shell ($env:PAGER -eq 'original pager' -and $env:GIT_PAGER -eq 'original git pager') 'Git log leaked pager settings'
    Assert-Shell ([bool](Get-Command z)) 'zoxide was not initialized'
    Assert-Shell ((Get-Command prompt).ScriptBlock.ToString().Contains('__zoxide_hook')) 'Starship replaced the zoxide recording hook'
    Assert-Shell ($global:__zoxide_prompt_old.ToString().Contains('Invoke Starship')) 'zoxide did not retain Starship'
    Assert-Shell ((Get-Content -LiteralPath $env:STARSHIP_CONFIG -Raw) -notmatch '\$rust') 'Windows prompt contains the Rust module'
    $env:STARSHIP_LOG = 'error'
    & starship.exe prompt | Out-Null
    Assert-Shell ($LASTEXITCODE -eq 0) 'Starship failed to render'
    Write-Output 'PowerShell shell checks passed.'
} finally {
    Set-Location -LiteralPath $originalLocation.Path
    $env:PAGER = $previousPager
    $env:GIT_PAGER = $previousGitPager
    $env:STARSHIP_LOG = $previousStarshipLog
    Remove-Item -LiteralPath 'Function:lf.exe' -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
