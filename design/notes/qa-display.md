# display-probe — resolution & input correctness at any window size

**0 FAIL / 15 checks**

| check | result | detail |
|---|---|---|
| logical backbuffer size | PASS | screen=(1600, 900) |
| aspect correct at (1600, 900) | PASS | picture 1600x900 letterbox (0, 0) |
| coordinate round-trip at (1600, 900) | PASS | max error 0px (tolerance 2) across 5 samples |
| aspect correct at (1280, 720) | PASS | picture 1280x720 letterbox (0, 0) |
| coordinate round-trip at (1280, 720) | PASS | max error 0px (tolerance 2) across 5 samples |
| aspect correct at (1920, 1080) | PASS | picture 1920x1080 letterbox (0, 0) |
| coordinate round-trip at (1920, 1080) | PASS | max error 0px (tolerance 2) across 5 samples |
| aspect correct at (2560, 720) | PASS | picture 1280x720 letterbox (640, 0) |
| coordinate round-trip at (2560, 720) | PASS | max error 0px (tolerance 2) across 5 samples |
| aspect correct at (1000, 1000) | PASS | picture 1000x562 letterbox (0, 219) |
| coordinate round-trip at (1000, 1000) | PASS | max error 2px (tolerance 2) across 5 samples |
| window click hits the minimap (non-native window) | PASS | window (1920, 1080): click (1768, 979) -> logical (1473, 815), camera moved 1648px |
| letterbox click ignored | PASS | state play->play |
| present() paints the logical picture into the window | PASS | window 1600x900: centre=(12, 34, 56) (want ~(12,34,56)), corner/bar=(12, 34, 56) |
| Alt+Enter switches display mode | PASS | windowed (1600, 900) -> (1024, 768) |
