#!/usr/bin/env sh
# Builds the official Ascon-AEAD128 reference (opt64) into a shared library.
# Requires gcc or clang. Run from the native/ directory: sh build.sh
set -e
case "$(uname -s)" in
  Darwin) OUT=libascon_aead128.dylib ;;
  *)      OUT=libascon_aead128.so ;;
esac
gcc -shared -fPIC -O2 -I. -o "$OUT" aead.c permutations.c printstate.c
echo "built $OUT"
