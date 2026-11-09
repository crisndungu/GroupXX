"""Ascon-AEAD128 via the official Ascon C reference implementation (NIST SP 800-232 design).

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].

The C sources in native/ come from github.com/ascon/ascon-c (opt64 build).
They are compiled into a shared library by native/build.sh (Linux or macOS),
or native/build.bat for Windows with MinGW-w64 gcc. If the library is absent,
ascon_available() returns False and the Ascon mode is skipped.

Output of this module matches the official known-answer test vectors (see
tests/test_ascon.py).
"""
import ctypes
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_NATIVE = os.path.join(_HERE, "..", "native")
KEY_LEN = 16
NONCE_LEN = 16
TAG_LEN = 16


def _library_path():
    if sys.platform.startswith("win"):
        name = "ascon_aead128.dll"
    elif sys.platform == "darwin":
        name = "libascon_aead128.dylib"
    else:
        name = "libascon_aead128.so"
    return os.path.join(_NATIVE, name)


_lib = None
try:
    _lib = ctypes.CDLL(_library_path())
    _lib.crypto_aead_encrypt.argtypes = [
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.c_char_p, ctypes.c_ulonglong,
        ctypes.c_char_p, ctypes.c_ulonglong,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ]
    _lib.crypto_aead_decrypt.argtypes = [
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulonglong,
        ctypes.c_char_p, ctypes.c_ulonglong,
        ctypes.c_char_p, ctypes.c_char_p,
    ]
except OSError:
    _lib = None


def ascon_available():
    return _lib is not None


def encrypt(key, nonce, aad, plaintext):
    if _lib is None:
        raise RuntimeError("native Ascon library not built; see native/build.sh")
    out = ctypes.create_string_buffer(len(plaintext) + TAG_LEN)
    out_len = ctypes.c_ulonglong(0)
    rc = _lib.crypto_aead_encrypt(out, ctypes.byref(out_len), plaintext, len(plaintext),
                                  aad, len(aad), None, nonce, key)
    if rc != 0:
        raise RuntimeError("ascon encrypt failed")
    return out.raw[: out_len.value]


def decrypt(key, nonce, aad, ciphertext):
    """Return plaintext, or None if the tag does not verify."""
    if _lib is None:
        raise RuntimeError("native Ascon library not built; see native/build.sh")
    out = ctypes.create_string_buffer(max(len(ciphertext), 1))
    out_len = ctypes.c_ulonglong(0)
    rc = _lib.crypto_aead_decrypt(out, ctypes.byref(out_len), None, ciphertext, len(ciphertext),
                                  aad, len(aad), nonce, key)
    if rc != 0:
        return None
    return out.raw[: out_len.value]
