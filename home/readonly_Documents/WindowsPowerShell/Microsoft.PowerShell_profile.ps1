# Set the console proxy port
$env:HTTP_PROXY="http://127.0.0.1:10808"
$env:HTTPS_PROXY="http://127.0.0.1:10808"

# Replace orginal Notepad with Notepad3
Set-Alias -Name notepad -Value notepad3
# uv tool: beet
$env:VISUAL = 'notepad'
$env:EDITOR = 'notepad'

# Fix Chinese character display
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

# Handle paths that contain escape characters
function cdl {
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path
    )

    Set-Location -LiteralPath $Path
}
