# Native Ascon-AEAD128

Files copied unchanged from github.com/ascon/ascon-c, crypto_aead/asconaead128/opt64
(aead.c, permutations.c, printstate.c, headers), plus crypto_aead.h from its tests folder.
Record the commit hash used in AI_LOG.md: [commit hash].

Build: `sh build.sh` (Linux or macOS) or `build.bat` (Windows with MinGW-w64).
The Python wrapper is src/ascon_native.py. Verified against the official
known-answer tests in tests/test_ascon.py.
