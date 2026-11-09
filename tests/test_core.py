"""Unit tests for the secure channel, gateway and replay protection.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Run from the project root: python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from crypto_modes import MODES, SecureChannel, available_modes  # noqa: E402
from demo import run  # noqa: E402


class ChannelTests(unittest.TestCase):
    def test_roundtrip_all_modes(self):
        for mode in available_modes():
            ch = SecureChannel(mode)
            blob = ch.seal(7, "plot-0", b"hello")
            self.assertEqual(ch.open(blob, "plot-0"), (7, b"hello"))

    def test_tamper_detected_in_aead_modes(self):
        for mode in ("aes-gcm", "chacha20", "ascon-aead128"):
            ch = SecureChannel(mode)
            blob = bytearray(ch.seal(1, "plot-0", b"moisture=50"))
            blob[-1] ^= 0x01
            with self.assertRaises(ValueError):
                ch.open(bytes(blob), "plot-0")

    def test_sequence_number_is_authenticated(self):
        ch = SecureChannel("ascon-aead128")
        blob = bytearray(ch.seal(1, "plot-0", b"x"))
        blob[3] ^= 0x01  # flip a bit in the sequence number
        with self.assertRaises(ValueError):
            ch.open(bytes(blob), "plot-0")

    def test_wrong_device_id_rejected(self):
        ch = SecureChannel("aes-gcm")
        blob = ch.seal(1, "plot-0", b"x")
        with self.assertRaises(ValueError):
            ch.open(blob, "plot-9")

    def test_plain_mode_accepts_tampered_payload(self):
        # Demonstrates the weakness that motivates the AEAD modes.
        ch = SecureChannel("plain")
        blob = bytearray(ch.seal(1, "plot-0", b"moisture=50"))
        blob[-1] ^= 0x01
        _, payload = ch.open(bytes(blob), "plot-0")
        self.assertNotEqual(payload, b"moisture=50")


class ReplayTests(unittest.TestCase):
    def test_replay_rejected_with_protection(self):
        result = run("chacha20", readings=10, attack=True, replay_protection=True)
        self.assertEqual(result["replays_accepted"], 0)

    def test_replay_accepted_without_protection(self):
        result = run("chacha20", readings=10, attack=True, replay_protection=False)
        self.assertGreater(result["replays_accepted"], 0)


if __name__ == "__main__":
    unittest.main()
