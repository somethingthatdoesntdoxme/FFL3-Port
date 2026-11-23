#!/usr/bin/env python3
"""Play a story route on the port and on the real game (PyBoy), and diff the checkpoints.

usage: tests/story_compare.py saga3.gb [route.txt] [--build build] [--port-only] [--keep DIR]

Each CHECK line has map, position, event flags (wC760-C77F), gold and bag, and party HP/max.
Map, position, flags and the bag must match; party HP is reported but only max HP is required to match (random
encounters on the way differ). Exit 1 on any mismatch, or if either side fails the route.
"""
import argparse, os, subprocess, sys, re

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
ap = argparse.ArgumentParser()
ap.add_argument('rom')
ap.add_argument('route', nargs='?', default=os.path.join(here, 'story', 'route.txt'))
ap.add_argument('--build', default=os.path.join(root, 'build'))
ap.add_argument('--port-only', action='store_true')
ap.add_argument('--dense', action='store_true', help='also compare place/flags/bag after every step (STEP lines)')
ap.add_argument('--keep', default='/tmp/story_compare')
a = ap.parse_args()
os.makedirs(a.keep, exist_ok=True)
env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')

def parse(text):
    out = []
    for l in text.splitlines():
        m = re.match(r'(CHECK|STEP|FAIL|DONE) (\S+) frame (\d+) map (\S+) pos (\d+),(\d+) flags (\S+) bag (\S+) members (\S+) party (.*)', l)
        if m:
            k, lab, fr, mp, r, c, fl, bg, mb, pa = m.groups()
            out.append(dict(kind=k, label=lab, frame=int(fr), map=mp, pos=(int(r), int(c)), flags=fl, bag=bg, members=mb,
                            party=pa.split(), maxhp=[p.split('/')[1] for p in pa.split()]))
    return out

if a.dense: env['FFL3_STORYDENSE'] = '1'
p = subprocess.run([os.path.join(a.build, 'ffl3'), os.path.abspath(a.rom), '--story', os.path.abspath(a.route)],
                   cwd=a.build, env=env, capture_output=True, text=True, timeout=3600)
port = parse(p.stdout)
open(os.path.join(a.keep, 'port.log'), 'w').write(p.stdout)
emu = []
if not a.port_only:
    try:
        import pyboy  # noqa: F401
        e = subprocess.run([sys.executable, os.path.join(root, 'tools', 'story_emu.py'), os.path.abspath(a.rom),
                            os.path.abspath(a.route), os.path.join(a.keep, 'emu.log'),
                            '--shots', os.path.join(a.keep, 'emu_shots')], capture_output=True, text=True, timeout=3600,
                           env=dict(os.environ, **({'FFL3_STORYDENSE': '1'} if a.dense else {})))
        emu = parse(open(os.path.join(a.keep, 'emu.log')).read())
    except ImportError:
        print('(PyBoy not installed: port only)')
        a.port_only = True

def flagdiff(x, y):
    bx, by = bytes.fromhex(x), bytes.fromhex(y)
    out = []
    for i in range(min(len(bx), len(by))):
        d = bx[i] ^ by[i]
        for k in range(8):
            if d & (0x80 >> k): out.append(('+' if bx[i] & (0x80 >> k) else '-') + '%02X' % (i * 8 + k))
    return ' '.join(out)

def shotdiff(label):
    """Share of pixels whose shade differs between the two screenshots (4 grey levels), and a
    side-by-side picture in KEEP/sbs/. None if either screenshot is missing."""
    try:
        from PIL import Image
    except ImportError:
        return None
    pp = os.path.join(a.build, 'story', label + '.bmp')
    ep = os.path.join(a.keep, 'emu_shots', label + '.png')
    if not (os.path.exists(pp) and os.path.exists(ep)): return None
    def shades(im):
        g = im.convert('L').crop((0, 0, 160, 144))
        data = g.tobytes()
        levels = sorted(set(data))
        rank = {v: min(3, round(i * 3 / max(1, len(levels) - 1))) for i, v in enumerate(levels)}
        return [rank[v] for v in data], g
    pa, pg = shades(Image.open(pp)); ea, eg = shades(Image.open(ep))
    d = sum(1 for x, y in zip(pa, ea) if x != y) / len(pa)
    os.makedirs(os.path.join(a.keep, 'sbs'), exist_ok=True)
    sbs = Image.new('L', (330, 144), 255); sbs.paste(pg, (0, 0)); sbs.paste(eg, (170, 0))
    sbs.save(os.path.join(a.keep, 'sbs', label + '.png'))
    return d

SHOT_LIMIT = 0.08          # more than 8% of the screen different: flag it (animation phases differ a bit)
ANIM_LIMIT = 0.75          # maps with a tile animation hook (sea, lava...): the phase follows the frame
                           # count, which differs - up to 75% (all sea) is a note
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
try:
    from ffl3data import Rom as _Rom
    _rom = _Rom(a.rom)
    def animated(mp): return _rom.map_header(int(mp, 16))['hook'] != 0
except Exception:
    def animated(mp): return False
bad = 0
rng_members = None
# Checkpoints whose screen is known to differ: '# known: ...' on the check line (a note, not a failure).
known = {}
for line in open(a.route):
    w = line.split('#', 1)
    t = w[0].split()
    if len(t) >= 2 and t[0] in ('check', 'peek') and len(w) > 1 and 'known:' in w[1]:
        known[t[1]] = w[1].split('known:', 1)[1].strip()
print(f'{"checkpoint":28} {"port":22} {"real game":22} result')
for i, pc in enumerate(port):
    ec = emu[i] if i < len(emu) else None
    pdesc = f'{pc["map"]} {pc["pos"][0]},{pc["pos"][1]} f{pc["frame"]}'
    if a.port_only or ec is None:
        res = 'ok' if pc['kind'] != 'FAIL' else 'FAIL'
        if pc['kind'] == 'FAIL': bad += 1
        print(f'{pc["label"][:28]:28} {pdesc:22} {"-":22} {res}')
        continue
    edesc = f'{ec["map"]} {ec["pos"][0]},{ec["pos"][1]} f{ec["frame"]}'
    probs = []; notes = []
    if pc['kind'] != ec['kind'] or pc['label'] != ec['label']: probs.append(f'{pc["kind"]} {pc["label"]} vs {ec["kind"]} {ec["label"]}')
    if pc['map'] != ec['map'] or pc['pos'] != ec['pos']: probs.append('place')
    if pc['flags'] != ec['flags']: probs.append('flags port vs game: ' + flagdiff(pc['flags'], ec['flags']))
    if pc['bag'] != ec['bag']: probs.append(f'bag port {pc["bag"]} vs game {ec["bag"]}')
    if pc['members'] != ec['members']:                     # after battles that went differently (max HP
        rng = pc['maxhp'] != ec['maxhp'] or (pc['members'], ec['members']) == rng_members   # differs too, or the
        if rng: rng_members = (pc['members'], ec['members'])   # same difference since): a meat eaten etc. - a note
        (notes if rng else probs).append(f'members port {pc["members"]} vs game {ec["members"]}')
    if pc['maxhp'] != ec['maxhp']: notes.append('(party ' + ' '.join(pc['party']) + ' vs ' + ' '.join(ec['party']) + ': random battles differ)')
    sd = shotdiff(pc['label']) if pc['kind'] != 'STEP' else None
    if sd is not None and sd > SHOT_LIMIT:
        if pc['label'] in known: notes.append(f'(screen {sd:.0%} different, known: {known[pc["label"]]})')
        elif sd <= ANIM_LIMIT and animated(pc['map']): notes.append(f'(screen {sd:.0%} different: animated tiles)')
        else: probs.append(f'screen {sd:.0%} different (see {a.keep}/sbs/{pc["label"]}.png)')
    bad += bool(probs)
    if pc['kind'] == 'STEP' and not probs: continue        # dense steps: only the ones that differ
    print(f'{pc["label"][:28]:28} {pdesc:22} {edesc:22} {"ok" if not probs else "DIFF: " + "; ".join(probs)}' + (' ' + ' '.join(notes) if notes else ''))
if len(emu) > len(port): print(f'real game got {len(emu) - len(port)} checkpoints further: {emu[len(port)]["label"]}'); bad += 1
if not port or port[-1]['kind'] != 'DONE': bad += 1
last = port[-1] if port else None
print()
nstep = sum(1 for c in port if c['kind'] == 'STEP')
print(f'{len(port) - nstep} checkpoints' + (f' + {nstep} steps' if nstep else '') + f', {"all match" if not bad else str(bad) + " problem(s)"}; port log {a.keep}/port.log'
      + ('' if a.port_only else f', game log {a.keep}/emu.log'))
sys.exit(1 if bad else 0)
