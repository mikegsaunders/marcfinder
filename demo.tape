# Records demo.gif for the README. Run with: vhs demo.tape
# Needs VHS (winget install charmbracelet.vhs) and ttyd (winget install tsl0922.ttyd).

Output demo.gif

Set Shell "pwsh"
Set FontSize 18
Set Width 1100
Set Height 720
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
# On Windows VHS can't capture at its default 50 fps but still writes 40 ms frames.
# Capture at 10 fps and play back at 0.4x so the GIF runs in real time.
Set Framerate 10
Set PlaybackSpeed 0.4

# VHS sets NO_COLOR for pwsh; clear it so marc shows colour.
# Also hide history suggestions and use a plain prompt on a clean screen.
Hide
Type "Remove-Item Env:NO_COLOR; Set-PSReadLineOption -PredictionSource None; function prompt { '> ' }; Clear-Host"
Enter
Sleep 1s
Show

Type "marc 245"
Sleep 250ms
Enter
Sleep 5s

Type "cls"
Enter

Type "marc ldr/06"
Sleep 250ms
Enter
Sleep 5s

Type "cls"
Enter

Type "marc isbn"
Sleep 250ms
Enter
Sleep 3.5s

Type "cls"
Enter

Type "marc -h 852"
Sleep 250ms
Enter
Sleep 5s

Type "cls"
Enter

Type "marc -v 010"
Sleep 250ms
Enter
Sleep 7s
