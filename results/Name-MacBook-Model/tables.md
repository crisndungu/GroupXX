# Results for Name-MacBook-Model

Statistic: median with interquartile range (Q1-Q3) over 10 repetitions. Ranges use the same IQR, so single slow repetitions do not decide a ranking.

Machine: Intel(R) Core(TM) i7-7567U CPU @ 3.50GHz | AES hardware: True | Python 3.9.6 | cryptography 50.0.2 | Ascon built: True | 2026-11-09 11:02:55

## Automated tests

Run 25, passed 25, failed 0, skipped 0 (none).

## Table 4 (this machine): median [Q1-Q3] us per message

| Mode | Seal 64 B | Open 64 B | Seal 256 B | Open 256 B |
|---|---|---|---|---|
| plain | 0.39 [0.37-0.46] | 0.58 [0.57-0.76] | 0.47 [0.47-0.50] | 0.60 [0.58-0.71] |
| aes-gcm | 8.56 [7.99-9.34] | 4.15 [4.00-4.33] | 8.70 [8.41-9.08] | 4.35 [4.17-5.08] |
| chacha20 | 9.56 [8.77-10.96] | 4.41 [4.28-4.49] | 9.37 [9.24-9.51] | 4.62 [4.54-4.77] |
| ascon-aead128 | 9.55 [9.25-9.90] | 4.86 [4.79-5.06] | 10.07 [9.74-10.56] | 5.42 [5.35-5.92] |

## Table 5 (this machine): AEAD ranking, fastest first

A gap is meaningful only if it exceeds the larger of the two interquartile ranges (Section 5.5).

- seal 64 B: aes-gcm < ascon-aead128 < chacha20. aes-gcm vs ascon-aead128: gap 0.99 us, within noise; ascon-aead128 vs chacha20: gap 0.01 us, within noise
- open 64 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 0.25 us, within noise; chacha20 vs ascon-aead128: gap 0.45 us, meaningful
- seal 256 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 0.67 us, meaningful; chacha20 vs ascon-aead128: gap 0.7 us, within noise
- open 256 B: aes-gcm < chacha20 < ascon-aead128. aes-gcm vs chacha20: gap 0.28 us, within noise; chacha20 vs ascon-aead128: gap 0.8 us, meaningful

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
