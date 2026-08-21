#Requires AutoHotkey v2.0

; Have the script automatically run again with administrator privileges
if !A_IsAdmin {
    try {
        if A_IsCompiled
            Run '*RunAs "' A_ScriptFullPath '"'
        else
            Run '*RunAs "' A_AhkPath '" "' A_ScriptFullPath '"'
    }
    ExitApp
}

; Check if the current window is in full-screen mode
IsFullScreen(winTitle := "A") {
    hwnd := WinExist(winTitle)
    if !hwnd
        return false

    WinGetPos &wx, &wy, &ww, &wh, "ahk_id " hwnd

    tolerance := 2
    monitorCount := MonitorGetCount()

    Loop monitorCount {
        MonitorGet A_Index, &left, &top, &right, &bottom

        mw := right - left
        mh := bottom - top

        if (
            Abs(wx - left) <= tolerance
            && Abs(wy - top) <= tolerance
            && Abs(ww - mw) <= tolerance
            && Abs(wh - mh) <= tolerance
        ) {
            return true
        }
    }

    return false
}

; japanese keyboard support
; 無変換
sc07B::Ctrl

; 変換 sc079::

; カタカナ|ひらがな|ローマ字 sc070::

; 半角|全角|漢字 sc029::

; mpv.exe
#HotIf WinActive("ahk_exe mpv.exe")
XButton1::Send("^{Left}")
XButton2::Send("^q")

; JPEGView.exe in full-screen mode
#HotIf WinActive("ahk_exe JPEGView.exe") && IsFullScreen("A")
XButton1::Right
XButton2::Left

; nightreign.exe
#HotIf WinActive("ahk_exe nightreign.exe")
XButton1::g
XButton2::f

; noita.exe
#HotIf WinActive("ahk_exe noita.exe")
XButton1::g
XButton2::f

; Global default settings
#HotIf
XButton1::Enter
XButton2::Backspace