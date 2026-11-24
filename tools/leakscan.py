#!/usr/bin/env python3
"""leakscan.py - fail if a file in the repo holds a run of bytes copied from the ROM.

Source derived from the ROM (C++, notes, hex in comments) is fine; ROM bytes are not. Any run of
at least --min bytes (default 32) that also occurs in the ROM is reported, unless it's filler
(fewer than 4 distinct byte values). Idea from SawGod's tools/leakscan.py.

usage: leakscan.py [--staged | --all | FILE...] [--min N] [--rom saga3.gb]
  --staged  the staged versions of the files about to be committed (the pre-commit hook)
  --all     every tracked file (default)
  ROM: --rom, else $FFL3_ROM, else /root/ffl3/rom/saga3.gb. No ROM: warns and passes.
  tools/leakscan.py --install-hook   writes .git/hooks/pre-commit
"""
import argparse, os, subprocess, sys

K = 16   # indexed gram length; every run >= 2K contains a K-aligned ROM gram

def filler(b): return len(set(b)) < 4

def index(rom):
    idx = {}
    for off in range(0, len(rom) - K + 1, K):
        g = rom[off:off + K]
        if not filler(g): idx.setdefault(g, []).append(off)
    return idx

def scan(data, rom, idx, minlen):
    i, n = 0, len(data)
    while i <= n - K:
        offs = idx.get(data[i:i + K])
        if not offs: i += 1; continue
        best = None
        for ro in offs:
            s, r = i, ro
            while s > 0 and r > 0 and data[s - 1] == rom[r - 1]: s -= 1; r -= 1
            e, q = i + K, ro + K
            while e < n and q < len(rom) and data[e] == rom[q]: e += 1; q += 1
            if best is None or e - s > best[2]: best = (s, r, e - s)
        if best[2] >= minlen and not filler(data[best[0]:best[0] + best[2]]):
            yield best
            i = best[0] + best[2]
        else:
            i += 1

def git(*a): return subprocess.run(['git', *a], capture_output=True, check=True).stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*')
    ap.add_argument('--staged', action='store_true')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--min', type=int, default=32)
    ap.add_argument('--rom', default=os.environ.get('FFL3_ROM', '/root/ffl3/rom/saga3.gb'))
    ap.add_argument('--install-hook', action='store_true')
    a = ap.parse_args()
    root = git('rev-parse', '--show-toplevel').decode().strip()
    os.chdir(root)
    if a.install_hook:
        hook = os.path.join(git('rev-parse', '--git-path', 'hooks').decode().strip(), 'pre-commit')
        with open(hook, 'w') as f: f.write('#!/bin/sh\nexec python3 tools/leakscan.py --staged\n')
        os.chmod(hook, 0o755)
        print('installed', hook); return 0
    if not os.path.exists(a.rom):
        print(f'leakscan: no ROM at {a.rom} (set FFL3_ROM); skipped', file=sys.stderr); return 0
    rom = open(a.rom, 'rb').read()
    idx = index(rom)
    if a.staged:
        names = [n for n in git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z').decode().split('\0') if n]
        blobs = ((n, git('show', ':' + n)) for n in names)
    else:
        names = a.files or [n for n in git('ls-files', '-z').decode().split('\0') if n]
        blobs = ((n, open(n, 'rb').read()) for n in names if os.path.isfile(n))
    bad = 0
    for name, data in blobs:
        for fo, ro, ln in scan(data, rom, idx, a.min):
            bank, addr = ro // 0x4000, ro % 0x4000 + (0x4000 if ro >= 0x4000 else 0)
            print(f'{name}: {ln} bytes at file offset {fo:#x} match the ROM at {bank:02X}:{addr:04X}')
            bad += 1
    if bad:
        print(f'leakscan: {bad} ROM byte run(s) found - no game data in the repo', file=sys.stderr); return 1
    print(f'leakscan: {len(names)} file(s) clean')
    return 0

if __name__ == '__main__':
    sys.exit(main())
