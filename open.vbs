Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
ps = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
code = shell.Run("""" & ps & """ -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & root & "\manage.ps1"" -Action Open", 0, True)
If code <> 0 Then MsgBox "VideoLibrary startup failed. See " & root & "\logs\startup.log and *.stderr.log. Run start.bat for details.", 48, "VideoLibrary"
