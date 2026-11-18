# Results for Name-Machine-Model

Statistic: median with interquartile range (Q1-Q3) over 10 repetitions. Ranges use the same IQR, so single slow repetitions do not decide a ranking.

Machine: Intel64 Family 6 Model 142 Stepping 9, GenuineIntel | AES hardware: None | Python 3.12.10 | cryptography 50.0.2 | Ascon built: True | 2026-11-18 15:20:01

## Automated tests

Run 25, passed 25, failed 0, skipped 0 (none).

## Table 4 (this machine): median [Q1-Q3] us per message

| Mode | Seal 64 B | Open 64 B | Seal 256 B | Open 256 B |
|---|---|---|---|---|
| plain | 0.44 [0.32-0.63] | 0.49 [0.45-1.11] | 0.44 [0.32-0.54] | 0.58 [0.51-0.85] |
| aes-gcm | 3.01 [2.05-5.20] | 3.95 [2.49-6.08] | 3.04 [2.25-4.91] | 3.54 [2.73-5.55] |
| chacha20 | 3.34 [2.79-5.38] | 3.11 [2.94-5.48] | 4.08 [3.31-6.61] | 5.76 [4.03-7.19] |
| ascon-aead128 | 5.25 [4.39-9.00] | 6.34 [4.50-9.23] | 8.90 [4.93-10.65] | 6.43 [5.21-11.62] |

## Table 5 (this machine): AEAD ranking, fastest first

A gap is meaningful only if it exceeds the larger of the two interquartile ranges (Section 5.5).

- seal 64 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 0.33 us, within noise; chacha20 vs ascon-aead128: gap 1.91 us, within noise
- open 64 B: chacha20 < aes-gcm < ascon-aead128. chacha20 vs aes-gcm: gap 0.84 us, within noise; aes-gcm vs ascon-aead128: gap 2.39 us, within noise
- seal 256 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 1.05 us, within noise; chacha20 vs ascon-aead128: gap 4.82 us, within noise
- open 256 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 2.22 us, within noise; chacha20 vs ascon-aead128: gap 0.67 us, within noise

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
