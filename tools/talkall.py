#!/usr/bin/env python3
"""Who's who on the map where a story route ends: walk up to each object the port's grid lists,
press A, and print the start of what it says (the port's FFL3_TEXTLOG, decoded).

usage: talkall.py saga3.gb route.txt [--build build]
Each object is one port run (route + the walk + face + a), so it takes a while on long routes."""
import os, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from ffl3data import Rom
from ffl3text import Text
rom, route = sys.argv[1], sys.argv[2]
build = sys.argv[sys.argv.index('--build') + 1] if '--build' in sys.argv else os.path.join(here, '..', 'build')
exe = os.path.join(build, 'ffl3'); grid = os.path.join(build, 'story', 'grid.txt')
env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', FFL3_TEXTLOG='1')
base = open(route).read().rstrip('\n') + '\n'
r0 = subprocess.run([exe, rom, '--story', route], env=env, capture_output=True, text=True, timeout=900)
base_n = sum(1 for l in r0.stderr.split('\n') if l.startswith('TEXT '))   # texts before the walk
import re
def bagof(out):
    m = re.findall(r' bag (\S+)', out)
    return set(m[-1].split(':', 1)[1].strip(',').split(',')) if m else set()
bag0 = bagof(r0.stdout)
objs = [tuple(map(int, l[4:].split(','))) for l in open(grid) if l.startswith('obj ')]
T = Text(Rom(rom))
for (r, c) in objs:
    best = None
    for d, (dr, dc) in (('U', (1, 0)), ('D', (-1, 0)), ('L', (0, 1)), ('R', (0, -1))):   # stand there, face d
        p = subprocess.run([sys.executable, os.path.join(here, 'plan.py'), rom, '-', '-', f'{r + dr},{c + dc}', '--grid', grid],
                           capture_output=True, text=True)
        if p.returncode == 0:
            walk = [l.split('   #')[0] for l in p.stdout.strip().split('\n')]
            if best is None or len(' '.join(walk)) < len(' '.join(best[0])): best = (walk, d)
    if not best: print(f'{r},{c}: no way to it'); continue
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        f.write(base + '\n'.join(best[0]) + f'\nface {best[1]}\na\ncheck talkall\n'); tmp = f.name
    out = subprocess.run([exe, rom, '--story', tmp], env=env, capture_output=True, text=True, timeout=900)
    os.unlink(tmp)
    texts = [l.split()[1] for l in out.stderr.split('\n') if l.startswith('TEXT ')]
    said = ''
    if len(texts) > base_n and 'talkall' in out.stdout:   # something new was said
        b, a = texts[-1].split(':'); ops, _ = T.parse(int(b, 16), int(a, 16)); said = T.render(ops).replace('\n', ' ')[:150]
    got = bagof(out.stdout) - bag0 if 'talkall' in out.stdout else set()
    print(f'{r},{c} (from {" | ".join(best[0])}, face {best[1]}): {said or "-"}' + (f'  [bag +{",".join(sorted(got))}]' if got else ''))
subprocess.run([exe, rom, '--story', route], env=env, capture_output=True, timeout=900)   # leave the grid as it was
