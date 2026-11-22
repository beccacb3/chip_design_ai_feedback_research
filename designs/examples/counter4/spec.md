# counter4

A 4-bit synchronous up-counter.

- `clk`: clock, rising-edge triggered.
- `reset`: active-high synchronous reset; sets `q` to 0.
- `en`: when high, `q` increments by 1 each cycle; when low, `q` holds.
- `q[3:0]`: counter value; wraps from 15 to 0.
