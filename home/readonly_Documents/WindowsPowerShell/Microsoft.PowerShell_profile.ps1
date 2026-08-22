# Set the console proxy port
$env:HTTP_PROXY="http://127.0.0.1:10808"
$env:HTTPS_PROXY="http://127.0.0.1:10808"

Set-Alias -Name notepad -Value notepad3

# uv tool: beet
$env:VISUAL = 'notepad'
$env:EDITOR = 'notepad'