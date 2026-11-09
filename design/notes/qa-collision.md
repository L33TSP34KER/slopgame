# qa-collision — crowd motion probe

**0 FAIL / 6 checks**

| check | result | detail |
|---|---|---|
| reachable move target found | PASS | target=(31, 66) |
| all units moved | PASS | min displacement 5.6 tiles, max 13.3 |
| group arrives and holds | PASS | arrived=True orders_cleared=True |
| no interpenetration (>= radius sum) | PASS | closest pair 0.795 tiles (archer/knight), 0 pairs <0.5: True |
| no unit ends inside a building | PASS | checked against every live building footprint |
| settled crowd does not shimmer | PASS | 0 reversals in 120 settled frames (approach-phase reversals 39, normal while funneling into slots) |
