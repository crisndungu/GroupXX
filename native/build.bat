@echo off
rem Windows build with MinGW-w64 gcc on PATH. Run from the native folder.
gcc -shared -O2 -I. -o ascon_aead128.dll aead.c permutations.c printstate.c
echo built ascon_aead128.dll
