# Integrated LiDAR Compression × TSN × Blockchain — Experimental Results
_Generated at 2025-09-23T22:37:37_
## Compression Findings
- BE=0.0 cm → best method **Huffman**, mean compression ratio 65.18%.
- BE=0.5 cm → best method **EB-HC-3D(Axis)**, mean compression ratio 28.99%.
- BE=1.0 cm → best method **EB-HC-3D(Axis)**, mean compression ratio 26.01%.
- BE=2.0 cm → best method **EB-HC-3D(Axis)**, mean compression ratio 23.14%.

## Scene-Level Averages
- campus: mean compressed size 543292 B (27.55% of raw, n=80).
- city: mean compressed size 504633 B (25.85% of raw, n=80).
- person: mean compressed size 480282 B (23.88% of raw, n=69).
- residential: mean compressed size 494109 B (24.79% of raw, n=80).
- road: mean compressed size 540528 B (27.69% of raw, n=80).

## TSNkit Simulation Metrics (two-hop 1 GbE TAS)
- campus: delay 4.351 ms, jitter 0.000 ms, 1 packets in cycle.
- city: delay 4.351 ms, jitter 0.000 ms, 1 packets in cycle.
- person: delay 4.351 ms, jitter 0.000 ms, 1 packets in cycle.
- residential: delay 4.351 ms, jitter 0.000 ms, 1 packets in cycle.
- road: delay 4.351 ms, jitter 0.000 ms, 1 packets in cycle.

## Blockchain/IPFS
On-chain CID success rate: 100.0% (21/21).

## Figures
- Compression ratios: outputs/paper/fig_cr_be*.png
- TSN delay/jitter: outputs/paper/fig_tsn_delay.png, fig_tsn_jitter.png

## Tables
- Algorithm overview: outputs/paper/table_1_methods.csv

## Notes
- TAS schedule built with guard alignment; simulation via tsnkit (ls algorithm). Compressed flows derived from KITTI multi-scene averages.
