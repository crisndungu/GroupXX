# Results for HP-Elitebook-820-G4

Statistic: median with interquartile range (Q1-Q3) over 10 repetitions. Ranges use the same IQR, so single slow repetitions do not decide a ranking.

Machine: Intel64 Family 6 Model 142 Stepping 9, GenuineIntel | AES hardware: None | Python 3.12.10 | cryptography 50.0.2 | Ascon built: True | 2026-11-18 15:22:15

## Automated tests

Run 25, passed 25, failed 0, skipped 0 (none).

## Table 4 (this machine): median [Q1-Q3] us per message

| Mode | Seal 64 B | Open 64 B | Seal 256 B | Open 256 B |
|---|---|---|---|---|
| plain | 0.36 [0.29-0.45] | 0.54 [0.51-0.60] | 0.37 [0.34-0.51] | 0.63 [0.57-0.79] |
| aes-gcm | 3.52 [3.16-4.42] | 3.47 [3.08-4.33] | 4.05 [3.32-4.44] | 4.10 [3.56-4.46] |
| chacha20 | 2.88 [2.50-3.17] | 4.34 [3.96-4.61] | 3.77 [3.32-4.53] | 4.96 [4.30-6.36] |
| ascon-aead128 | 7.73 [7.18-8.55] | 6.54 [6.16-7.31] | 9.35 [7.49-10.34] | 7.40 [6.07-7.84] |

## Table 5 (this machine): AEAD ranking, fastest first

A gap is meaningful only if it exceeds the larger of the two interquartile ranges (Section 5.5).

- seal 64 B: chacha20 < aes-gcm < ascon-aead128. chacha20 vs aes-gcm: gap 0.64 us, within noise; aes-gcm vs ascon-aead128: gap 4.22 us, meaningful
- open 64 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 0.87 us, within noise; chacha20 vs ascon-aead128: gap 2.2 us, meaningful
- seal 256 B: chacha20 < aes-gcm < ascon-aead128. chacha20 vs aes-gcm: gap 0.28 us, within noise; aes-gcm vs ascon-aead128: gap 5.31 us, meaningful
- open 256 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 0.86 us, within noise; chacha20 vs ascon-aead128: gap 2.45 us, meaningful

## Table 6 (this machine): replay experiment, summed over repetitions

| Guard | Replayed | Accepted | Rejected | Legitimate messages rejected |
|---|---|---|---|---|
| disabled, aes-gcm | 100 | 100 | 0 | 0 |
| disabled, chacha20 | 100 | 100 | 0 | 0 |
| disabled, ascon-aead128 | 100 | 100 | 0 | 0 |
| disabled, plain | 100 | 100 | 0 | 0 |
| enabled, aes-gcm | 100 | 0 | 100 | 0 |
| enabled, chacha20 | 100 | 0 | 100 | 0 |
| enabled, ascon-aead128 | 100 | 0 | 100 | 0 |
| enabled, plain | 100 | 0 | 100 | 0 |
