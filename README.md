# Smart Plant Monitor: Lightweight Cryptography Proof-of-Concept

CMP-7037A/6060A Assignment 002, Topic 9: Lightweight Cryptography for Resource-Constrained IoT Devices.
Group: GroupXX

## What this does
Simulated soil sensors send moisture and temperature readings to a gateway.
The same data is run in three modes: plaintext (baseline), AES-GCM, and ChaCha20-Poly1305.
A replay attacker records sealed messages and resends them. The gateway rejects replays
when sequence-number protection is enabled.

## Setup
Python 3.10 or later, gcc (for the Ascon library), and a Mosquitto broker for the live run.

    pip install -r requirements.txt
    cd native && sh build.sh && cd ..        (Windows: build.bat with MinGW-w64 gcc)
    mosquitto -p 1883                        (live run only; Windows: use the Mosquitto installer)

## Run
    python src/demo.py --mode chacha20 --readings 50 --attack
    python src/demo.py --mode ascon-aead128 --readings 50 --attack --no-replay-protection
    python src/benchmark.py --messages 5000 --payload 64
    python src/run_live.py --mode aes-gcm --seconds 60 --attack     (needs the broker running)
    open http://localhost:8080                                        (dashboard during the live run)
    python -m unittest discover -s tests -v

## Layout
    src/crypto_modes.py     message protection (plain, AES-GCM, ChaCha20-Poly1305, Ascon-AEAD128)
    src/ascon_native.py     wrapper for the official Ascon C reference (native/)
    src/sensor.py           simulated soil sensor
    src/gateway.py          replay guard and gateway
    src/attack.py           replay attacker
    src/transport_mqtt.py   MQTT publisher and gateway subscriber (WP1)
    src/dashboard.py        live plant dashboard and status logic (WP4)
    src/run_live.py         live end-to-end run over MQTT
    src/demo.py             in-process end-to-end run
    src/benchmark.py        overhead and timing per message
    native/                 official Ascon-AEAD128 C sources and build scripts
    tests/                  unit, known-answer (200 official Ascon vectors) and MQTT tests (15 tests)
    results/                benchmark output
    AI_LOG.md            declaration of AI-assisted code
    WORK_PACKAGES.md     team plan and dates

## Test status (last run)
- 15 tests pass, including all 200 official Ascon-AEAD128 known-answer vectors and an MQTT round trip through a local Mosquitto 2.0.18 broker.
- A live run with a replay attack at 30 seconds: 108 messages accepted, 10 replays rejected, and the dashboard showed the alert state.

## Ascon implementation note (important for the report)
The Python package "ascon" (v0.0.9) implements the earlier Ascon v1.2 design. It does not match the official known-answer vectors, so it is not used. The project uses the official C reference from github.com/ascon/ascon-c, which matches the vectors. Benchmark timings include the Python-to-C call overhead. Timings on a microcontroller will differ, and the report must say so.

## Known limitations (for the report)
- Random 96-bit nonces are used per message. AES-GCM and ChaCha20-Poly1305 both require nonces never to repeat under the same key. Discuss the message-count limit and the alternative of a counter-based nonce.
- The replay guard keeps the last sequence number per device in memory. If a device reboots and resets its counter, the gateway rejects its messages until the counter passes the stored value. A real design needs a persisted counter or a handshake.
- Keys are generated in memory and not provisioned to devices. Key distribution is out of scope and should be discussed as a limitation.
- Timings in results/ were measured on one development machine. They are not representative of a microcontroller. Measure on the hardware available to the group, or discuss the gap explicitly.

- The simulated moisture is a random walk with no watering events. Plants will tend to dry out over a long run.
- The benchmark runs on one development machine. Measure on at least two machines and, if possible, one constrained device (WP3).
- The Ascon C code is compiled for the local machine. Constrained devices need the reference's embedded builds (for example armv7m or avr folders in ascon-c), which the team should evaluate but not assume.

## Next steps
- Measure on a second machine and, if available, a constrained device (WP3).
- Write the Ascon evaluation section (WP2): cipher choice, nonce handling, and the difference between the Python and C timings.
- Add a persisted replay counter or discuss its absence (WP2 and WP4).
