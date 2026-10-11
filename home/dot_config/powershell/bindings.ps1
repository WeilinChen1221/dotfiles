if (-not (Get-Module PSReadLine)) { return }

function Get-DotfilesHistoryMatches {
    param([string[]]$History, [string]$Query)
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    for ($index = $History.Count - 1; $index -ge 0; $index--) {
        $entry = $History[$index]
        if ($entry.IndexOf($Query, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $seen.Add($entry)) {
            $entry
        }
    }
}

function Invoke-DotfilesHistorySearch {
    param([int]$Direction)
    $line = $null
    $cursor = 0
    [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
    $state = $global:DotfilesHistorySearchState
    if (-not $state -or $state.LastLine -cne $line) {
        $state = @{
            Original = $line
            LastLine = $line
            Index = -1
            Matches = @(Get-DotfilesHistoryMatches `
                -History @([Microsoft.PowerShell.PSConsoleReadLine]::GetHistoryItems().CommandLine) -Query $line)
        }
        $global:DotfilesHistorySearchState = $state
    }
    $nextIndex = $state.Index + $Direction
    if ($nextIndex -ge $state.Matches.Count -or $nextIndex -lt -1) { return }
    $replacement = if ($nextIndex -eq -1) { $state.Original } else { $state.Matches[$nextIndex] }
    [Microsoft.PowerShell.PSConsoleReadLine]::Replace(0, $line.Length, $replacement)
    [Microsoft.PowerShell.PSConsoleReadLine]::SetCursorPosition($replacement.Length)
    $state.Index = $nextIndex
    $state.LastLine = $replacement
}

foreach ($mode in 'Insert', 'Command') {
    Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+RightArrow' -Function ForwardWord
    Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+LeftArrow' -Function BackwardWord
    Set-PSReadLineKeyHandler -ViMode $mode -Chord UpArrow -BriefDescription SubstringHistoryUp `
        -ScriptBlock { Invoke-DotfilesHistorySearch 1 }
    Set-PSReadLineKeyHandler -ViMode $mode -Chord DownArrow -BriefDescription SubstringHistoryDown `
        -ScriptBlock { Invoke-DotfilesHistorySearch -1 }
    Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+f' -BriefDescription FindVisibleFile `
        -ScriptBlock { Invoke-DotfilesFilePicker }
    Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+\' -BriefDescription ToggleSuggestions -ScriptBlock {
        if ((Get-Command Set-PSReadLineOption).Parameters.ContainsKey('PredictionSource')) {
            $source = if ((Get-PSReadLineOption).PredictionSource -eq 'None') { 'History' } else { 'None' }
            Set-PSReadLineOption -PredictionSource $source
        }
    }
    Set-PSReadLineKeyHandler -ViMode $mode -Chord Enter -BriefDescription AutoCd -ScriptBlock {
        $global:DotfilesHistorySearchState = $null
        $line = $null
        $cursor = 0
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
        $directory = Get-DotfilesAutoCdPath $line
        if ($directory) {
            $command = 'Set-Location -LiteralPath ' + (ConvertTo-DotfilesPathToken $directory)
            [Microsoft.PowerShell.PSConsoleReadLine]::Replace(0, $line.Length, $command)
        }
        [Microsoft.PowerShell.PSConsoleReadLine]::ValidateAndAcceptLine()
    }
    if (Get-Module PSFzf) {
        Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+r' -BriefDescription FzfHistory `
            -ScriptBlock { Invoke-FzfPsReadlineHandlerHistory }
        Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+t' -BriefDescription FzfFiles `
            -ScriptBlock { Invoke-FzfPsReadlineHandlerProvider }
        Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Alt+c' -BriefDescription FzfDirectory `
            -ScriptBlock { Invoke-FzfPsReadlineHandlerSetLocation }
    } else {
        Set-PSReadLineKeyHandler -ViMode $mode -Chord 'Ctrl+r' -Function ReverseSearchHistory
    }
}
