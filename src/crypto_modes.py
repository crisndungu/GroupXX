"""Message protection modes for constrained IoT sensor messages.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].

Modes:
    plain      no protection (baseline only)
    aes-gcm    AES-128-GCM, 12-byte nonce, 16-byte tag (cryptography library)
    chacha20   ChaCha20-Poly1305, 12-byte nonce, 16-byte tag (cryptography library)
    ascon-aead128  Ascon-AEAD128, 16-byte key/nonce/tag, NIST SP 800-232 design,
               via the official C reference (src/ascon_native.py). Needs native build.

Wire format for every mode:
    header  = 4-byte big-endian sequence number
    plain   : header | payload
    AEAD    : header | nonce | ciphertext+tag
The header is authenticated as associated data, so an attacker cannot change
the sequence number without the tag check failing.
"""
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

import ascon_native

_HEADER = struct.Struct(">I")
TAG_LEN = 16
MODES = ("plain", "aes-gcm", "chacha20", "ascon-aead128")


def available_modes():
    """Modes usable on this machine (Ascon needs the native library built)."""
    return tuple(m for m in MODES if m != "ascon-aead128" or ascon_native.ascon_available())


class SecureChannel:
    """Seals and opens sensor messages for one mode.

    Plain mode provides no confidentiality or integrity. It is a baseline for
    the report's overhead and performance comparison only.
    """

    def __init__(self, mode, key=None):
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        self.mode = mode
        self._key = None
        self._aead = None
        if mode == "aes-gcm":
            self._key = key or AESGCM.generate_key(bit_length=128)
            self._aead = AESGCM(self._key)
            self._nonce_len = 12
        elif mode == "chacha20":
            self._key = key or ChaCha20Poly1305.generate_key()
            self._aead = ChaCha20Poly1305(self._key)
            self._nonce_len = 12
        elif mode == "ascon-aead128":
            if not ascon_native.ascon_available():
                raise RuntimeError("native Ascon library not built; see native/build.sh")
            self._key = key or os.urandom(ascon_native.KEY_LEN)
            self._nonce_len = ascon_native.NONCE_LEN
        else:
            self._nonce_len = 0

    def _encrypt(self, nonce, aad, payload):
        if self.mode == "ascon-aead128":
            return ascon_native.encrypt(self._key, nonce, aad, payload)
        return self._aead.encrypt(nonce, payload, aad)

    def _decrypt(self, nonce, aad, body):
        if self.mode == "ascon-aead128":
            result = ascon_native.decrypt(self._key, nonce, aad, body)
            if result is None:
                raise ValueError("authentication failed")
            return result
        try:
            return self._aead.decrypt(nonce, body, aad)
        except Exception as exc:  # cryptography raises InvalidTag
            raise ValueError("authentication failed") from exc

    def seal(self, seq, device_id, payload):
        header = _HEADER.pack(seq)
        if self.mode == "plain":
            return header + payload
        nonce = os.urandom(self._nonce_len)
        aad = device_id.encode() + header
        return header + nonce + self._encrypt(nonce, aad, payload)

    def open(self, blob, device_id):
        """Return (seq, payload). Raises ValueError if an AEAD message is invalid."""
        if len(blob) < _HEADER.size:
            raise ValueError("message too short")
        header = blob[: _HEADER.size]
        (seq,) = _HEADER.unpack(header)
        if self.mode == "plain":
            return seq, blob[_HEADER.size :]
        start = _HEADER.size + self._nonce_len
        if len(blob) < start + TAG_LEN:
            raise ValueError("message too short")
        nonce = blob[_HEADER.size : start]
        body = blob[start:]
        aad = device_id.encode() + header
        return seq, self._decrypt(nonce, aad, body)

    def overhead(self):
        """Bytes added to each payload by this mode."""
        if self.mode == "plain":
            return _HEADER.size
        return _HEADER.size + self._nonce_len + TAG_LEN
