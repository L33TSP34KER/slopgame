# qa-xwindow — real X server test (window + real cursor clicks)

**0 FAIL / 10 checks**

| check | result | detail |
|---|---|---|
| 1920x1080: game window exists | PASS | window id=0x200008 |
| 1920x1080: window is 16:9 and fits the screen | PASS | window 1600x900+160+90 on a 1920x1080 screen (1600x900 only fits screens >=1640x980) |
| 1920x1080: click on empty ground clears selection | PASS | sel ['hero'] -> [] |
| 1920x1080: click at the units selects them | PASS | unit_px=[780, 528] -> sel ['hero'] |
| 1920x1080: click still lands after resizing window to 1100x700 | PASS | window 1600x900 -> 1100x700, unit_px=[780, 528], sel ['hero'] |
| 1366x768: game window exists | PASS | window id=0x200008 |
| 1366x768: window is 16:9 and fits the screen | PASS | window 1152x648+107+60 on a 1366x768 screen (1600x900 only fits screens >=1640x980) |
| 1366x768: click on empty ground clears selection | PASS | sel ['hero'] -> [] |
| 1366x768: click at the units selects them | PASS | unit_px=[780, 528] -> sel ['hero'] |
| 1366x768: click still lands after resizing window to 1100x700 | PASS | window 1152x648 -> 1100x700, unit_px=[780, 528], sel ['hero'] |

Screenshots: `design/notes/shots/xwin-*.png`
