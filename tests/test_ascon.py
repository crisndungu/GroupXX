"""Known-answer tests for the native Ascon-AEAD128 wrapper.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Vectors: tests/ascon_kat_subset.txt, first 200 records of LWC_AEAD_KAT_128_128.txt
from github.com/ascon/ascon-c (official NIST LWC known-answer file).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import ascon_native  # noqa: E402


def load_vectors(path):
    vectors, current = [], {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = (x.strip() for x in line.split("=", 1))
                if k == "Count" and current:
                    vectors.append(current)
                    current = {}
                current[k] = v
    if current:
        vectors.append(current)
    return vectors


@unittest.skipUnless(ascon_native.ascon_available(), "native Ascon library not built")
class AsconKatTests(unittest.TestCase):
    def test_official_vectors_match(self):
        vectors = load_vectors(os.path.join(HERE, "ascon_kat_subset.txt"))
        self.assertGreaterEqual(len(vectors), 200)
        for v in vectors:
            key = bytes.fromhex(v["Key"])
            nonce = bytes.fromhex(v["Nonce"])
            ad = bytes.fromhex(v["AD"])
            pt = bytes.fromhex(v["PT"])
            ct = bytes.fromhex(v["CT"])
            with self.subTest(count=v["Count"]):
                self.assertEqual(ascon_native.encrypt(key, nonce, ad, pt), ct)
                self.assertEqual(ascon_native.decrypt(key, nonce, ad, ct), pt)

    def test_bad_tag_returns_none(self):
        key, nonce = os.urandom(16), os.urandom(16)
        ct = bytearray(ascon_native.encrypt(key, nonce, b"ad", b"moisture=50"))
        ct[-1] ^= 0x01
        self.assertIsNone(ascon_native.decrypt(key, nonce, b"ad", bytes(ct)))


if __name__ == "__main__":
    unittest.main()
