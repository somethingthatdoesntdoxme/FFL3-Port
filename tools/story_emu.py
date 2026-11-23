#!/usr/bin/env python3
"""Play a story route (tests/story/route.txt) on the real game in PyBoy, logging checkpoints.

usage: story_emu.py saga3.gb route.txt out.log [--shots DIR] [--state-every N]

The same step rules as the port's --story player (src/story.cpp), so the two logs can be
diffed with tests/story_compare.py. Needs PyBoy (pip install pyboy).

"Free" = the field loop got as far as reading a direction (00:07D6: after the step, the step
events and the conveyor had nothing to do) in the last couple of frames, two frames running,
and the leader stands on the block grid.
While not free (text, battles, menus, map fades) the player mashes A, like the port's.
"""
import sys, os, argparse
from pyboy import PyBoy

ap = argparse.ArgumentParser()
ap.add_argument('rom'); ap.add_argument('route'); ap.add_argument('log')
ap.add_argument('--shots')
a = ap.parse_args()

pb = PyBoy(a.rom, window='null', sound_emulated=False)
pb.set_emulation_speed(0)
mem = pb.memory
st = {'loop': False}
pb.hook_register(0, 0x0265, lambda ctx: st.__setitem__('loop', True), None)
# 00:07D6 is only reached once the step (01:43F9), the step events (00:08F3) and the conveyor
# (01:4BF6) have all had their turn with nothing to do: the game is waiting for a direction.
st['ready'] = -10
pb.hook_register(0, 0x07d6, lambda ctx: st.__setitem__('ready', frame), None)
pb.hook_register(1, 0x6fd4, lambda ctx: st.__setitem__('shop', frame), None)   # a shop opens
if os.environ.get('STORY_TXT'):                           # debug: log every text the game opens (00:3211)
    pb.hook_register(0, 0x3211, lambda ctx: print(f'TXT frame {frame} bank {pb.memory[0x2000] if False else "?"}'), None)

frame = 0
held = set()
log = open(a.log, 'w')

last_pos = {'row': 0, 'col': 0, 'map': 0}
def state():
    """Map and block of the leader. The block only updates when the leader is lined up on one
    (mid-step the scroll would round to the next block early going up or left)."""
    sy = mem[0xc6e4] | mem[0xc6e5] << 8
    sx = mem[0xc6e6] | mem[0xc6e7] << 8
    aligned = sy % 16 == 0 and sx % 16 == 0 and mem[0xc6ef] == 0   # wC6EF: a step still running (01:43F9)
    if sy % 16 == 0 and sx % 16 == 0 or mem[0xc6e8] != last_pos['map']:
        last_pos.update(map=mem[0xc6e8], row=((sy + 0x50) >> 4) & 63, col=((sx + 0x50) >> 4) & 63)
    return {'map': mem[0xc6e8], 'row': last_pos['row'], 'col': last_pos['col'], 'aligned': aligned}

free_run = 0
no_battles = [False]
npcs_still = [False]
def _no_wander(_):                                        # 01:5092: just after the wander roll (00:39D5)
    if npcs_still[0]: mem[0xff90] |= 0x04                 # & $FC != 0: no step this time
pb.hook_register(1, 0x5092, _no_wander, None)
WATCH = {int(x, 16): -1 for x in os.environ.get('STORY_WATCH', '').split(',') if x}

def tick(keys=()):
    """One frame with these buttons held; tracks how many frames in a row we've been free."""
    global frame, free_run
    for k in list(held):
        if k not in keys: pb.button_release(k); held.discard(k)
    for k in keys:
        if k not in held: pb.button_press(k); held.add(k)
    st['loop'] = False
    if no_battles[0]: mem[0xca2b] = 0                    # 01:4617: rate 0 = no random battles
    pb.tick(1, bool(a.shots))
    frame += 1
    s = state()
    if WATCH:                                             # debug: STORY_WATCH=c206,c769 logs changes
        for ad in WATCH:
            v = mem[ad]
            if WATCH[ad] != v:
                print(f'WATCH {ad:04x} {WATCH[ad]:02x} -> {v:02x} frame {frame} pos {s["row"]},{s["col"]}', flush=True)
                WATCH[ad] = v
    free_run = free_run + 1 if (frame - st['ready'] <= 1 and s['aligned']) else 0
    return s

def free(): return free_run >= 2

def flags():                                              # event flags wC760, chest flags wC780
    return bytes(mem[0xc760 + i] for i in range(64)).hex()

def party():
    out = []
    for i in range(4):
        b = 0xc500 + 0x60 * i
        out.append('%d/%d' % (mem[b + 0x10] | mem[b + 0x11] << 8, mem[b + 0x12] | mem[b + 0x13] << 8))
    return ' '.join(out)

def quiet_until_free(limit, need=2):                      # no keys: free for `need` frames running (or give up)
    n = 0
    while n < limit and free_run < need:
        tick(); n += 1

pending_step = ['']

def mash_until_free(limit, start=False):
    n = 0
    while not free():
        if n >= limit: return False
        k = ()
        if n >= 32 and 8 <= n % 16 < 10 and free_run == 0 and mem[0xc6ef] == 0: k = ('a', 'start') if start and (n // 16) % 4 == 3 else ('a',)
        tick(k); n += 1
    if pending_step[0]: emit('STEP', pending_step[0]); pending_step[0] = ''   # dense runs
    return True

DIRS = {'U': 'up', 'D': 'down', 'L': 'left', 'R': 'right'}
KEYS = {'A': 'a', 'B': 'b', 'S': 'start', 'E': 'select', **DIRS}

def bag():                                                # wC6E0 gold, wC6FF: 24 (id, count) pairs
    g = mem[0xc6e0] | mem[0xc6e1] << 8 | mem[0xc6e2] << 16
    out = f'g{g}:'
    for i in range(24):
        if mem[0xc6ff + i * 2] != 0xff: out += f'{mem[0xc6ff + i * 2]:02X}*{mem[0xc700 + i * 2]},'
    return out

def members():                                            # wC500 + $60 n: +3 who, +$40-$4F items
    return ','.join(f'{mem[0xc500 + i * 0x60 + 3]:02X}/' + ''.join(f'{mem[0xc540 + i * 0x60 + k]:02X}' for k in range(16))
                    for i in range(5))

def emit(kind, label, extra=''):
    s = state()
    line = f'{kind} {label} frame {frame} map {s["map"]:02X} pos {s["row"]},{s["col"]} flags {flags()} bag {bag()} members {members()} party {party()}{extra}'
    print(line); log.write(line + '\n'); log.flush()
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
        pb.screen.image.save(os.path.join(a.shots, f'{label}.png'))

def fail(why):
    emit('FAIL', why.replace(' ', '_'))
    sys.exit(1)

steps = [l.split('#')[0].strip() for l in open(a.route)]
section = 'start'
# debug: STORY_RESUME=FILE:N loads a state saved by STORY_STATE (FILE) and carries on from route
# line N; before it only the settings (battles, npcs) are applied. For exploring the real game.
resume_from = 0
if os.environ.get('STORY_RESUME'):
    rf, rn = os.environ['STORY_RESUME'].rsplit(':', 1)
    with open(rf, 'rb') as f: pb.load_state(f)
    resume_from = int(rn)
for ln, line in enumerate(steps, 1):
    if not line: continue
    w = line.split()
    op = w[0]
    if ln < resume_from and op not in ('battles', 'npcs'): continue
    if op == '==':
        section = '_'.join(w[1:]); continue
    if op == 'new':                                       # title, naming, opening: until free
        def press(k, n=1):
            for _ in range(n):
                for _ in range(3): tick((k,))
                for _ in range(17): tick()
        for _ in range(600): tick()                       # the same presses as run/probe.txt
        press('start'); [tick() for _ in range(60)]; press('a'); [tick() for _ in range(60)]; press('a', 400)
        for _ in range(4):
            press('start'); [tick() for _ in range(60)]; press('a', 10)
        press('start'); [tick() for _ in range(60)]
        if not mash_until_free(60000): fail(f'line {ln} never got control')
    elif op == 'go':                                      # go D3 L2: end up 3 blocks down, ...
        for tok in w[1:]:
            d, n = DIRS[tok[0]], int(tok[1:] or 1)
            vert = tok[0] in 'UD'; sign = 1 if tok[0] in 'DR' else -1
            if not mash_until_free(20000): fail(f'line {ln} stuck before {tok}')
            map0 = state()['map']; prev = state()['row' if vert else 'col']; moved = 0; guard = 0
            while moved < n and state()['map'] == map0:
                if not mash_until_free(20000): fail(f'line {ln} stuck in {tok}')
                if state()['map'] != map0: break
                s0 = state(); t = 0; idle = 0
                while True:
                    s = tick((d,)); t += 1
                    idle = 0 if st['loop'] else idle + 1      # the overworld loop skips frames: only
                    if (s['map'], s['row'], s['col']) != (s0['map'], s0['row'], s0['col']) or idle >= 8: break   # 8 in a row = text / battle
                    if t > 120: fail(f'line {ln} blocked going {tok} at {s0["map"]:02X} {s0["row"]},{s0["col"]}')
                now = state()['row' if vert else 'col']
                if os.environ.get("STORY_DEBUG"):
                    print('try', guard, tok, 'from', s0['row'], s0['col'], 'to', state()['row'], state()['col'], 't', t, 'loop', st['loop'], 'c6e3', mem[0xc6e3], 'c2e0', hex(mem[0xc2e0]), 'c6ef', mem[0xc6ef])
                if now != prev:
                    dd = (now - prev) * sign
                    if dd < -32: dd += 64
                    if dd > 32: dd -= 64
                    moved += dd; prev = now
                guard += 1
                if guard > 400: fail(f'line {ln} wandering in {tok}')
                tick()
    elif op == 'ride':                                    # ride D: hold it over moving floors (sideways off
        d = DIRS[w[1][0]]                                 # them, against them) until a still block
        if not mash_until_free(20000): fail(f'line {ln} stuck before ride')
        s0 = state(); f = 0
        while True:
            s = tick((d,)); f += 1
            moved = (s['map'], s['row'], s['col']) != (s0['map'], s0['row'], s0['col'])
            if moved and mem[0xc6ef] == 0 and (mem[0xc2f0] & 0xc0) != 0x80: break   # wC2F0: attr under the leader
            if f > 1200: fail(f'line {ln} riding too long')
    elif op == 'a':                                       # press A (talk / examine), then until free
        if not mash_until_free(20000): fail(f'line {ln} stuck before A')
        tick(('a',)); tick(('a',)); tick(); tick()
        if not mash_until_free(20000): fail(f'line {ln} stuck after A')
    elif op == 'shop':                                    # talk to a seller: through the speech, then out (B)
        if not mash_until_free(20000): fail(f'line {ln} stuck before shop')
        st['shop'] = -1
        tick(('a',)); tick(('a',)); tick(); tick()
        n = 0
        while not free() and st.get('shop', -1) < 0:
            if n >= 20000: fail(f'line {ln} no shop'); break
            tick(('a',) if n % 16 < 2 else ()); n += 1
        n = 0
        while not free():
            if n >= 20000: fail(f'line {ln} stuck in the shop'); break
            tick(('b',) if n % 16 < 2 else ()); n += 1
    elif op == 'jump':                                    # B: jump the way the leader faces
        if not mash_until_free(20000): fail(f'line {ln} stuck before jump')
        tick(('b',)); tick(('b',)); tick(); tick()
        if not mash_until_free(20000): fail(f'line {ln} stuck after jump')
    elif op == 'face':                                    # face D: turn without moving (a tap)
        mash_until_free(20000)
        tick((DIRS[w[1][0]],)); tick()
        quiet_until_free(60)                              # a turn: no A (it could talk)
        mash_until_free(20000)
    elif op == 'boost':                                   # test helper: HP 500, MP 200, str/def/mag/agi 60
        for i in range(5):
            b = 0xc500 + i * 0x60
            if mem[b + 3] == 0xff or (mem[b + 0x12] | mem[b + 0x13]) == 0: continue
            mem[b + 1] = 0                                # +1 status (+0 is the race - see 0B:6683)
            for o in (0x10, 0x12): mem[b + o] = 500 & 0xff; mem[b + o + 1] = 500 >> 8
            for o in (0x14, 0x16): mem[b + o] = 200; mem[b + o + 1] = 0
            for o in range(0x18, 0x1c): mem[b + o] = int(w[1]) if len(w) > 1 else 60   # boost N: stats N
    elif op == 'heal':                                    # test helper: full HP/MP, no status (records at C500)
        for i in range(5):
            b = 0xc500 + i * 0x60
            if mem[b + 3] == 0xff or (mem[b + 0x12] | mem[b + 0x13]) == 0: continue
            mem[b + 1] = 0                                # +1 status (+0 is the race - see 0B:6683)
            for o in (0x10, 0x14): mem[b + o] = mem[b + o + 2]; mem[b + o + 1] = mem[b + o + 3]
    elif op == 'npcs':                                    # npcs still / wander
        npcs_still[0] = len(w) > 1 and w[1] == 'still'
    elif op == 'battles':                                 # random encounters on / off
        no_battles[0] = len(w) > 1 and w[1] == 'off'
    elif op == 'wait':
        for _ in range(int(w[1])): tick()
    elif op == 'keys':                                    # raw presses: A B S U D L R, wN = wait
        for tok in w[1:]:
            if tok[0] == 'w': [tick() for _ in range(int(tok[1:]))]; continue
            hold = int(tok[1:]) if len(tok) > 1 else 3    # U20: held 20 frames
            for _ in range(hold): tick((KEYS[tok[0]],))
            for _ in range(12): tick()
    elif op == 'settle':
        if not mash_until_free(20000): fail(f'line {ln} never settled')
    elif op == 'peek':
        emit('CHECK', w[1] if len(w) > 1 else f'{section}_{ln}')
    elif op == 'check':
        mash_until_free(20000); emit('CHECK', w[1] if len(w) > 1 else f'{section}_{ln}')
    elif op == 'expect':                                  # expect map MM [row col]
        mash_until_free(20000)
        s = state()
        want = (int(w[2], 16),) + tuple(int(x) for x in w[3:5])
        got = (s['map'], s['row'], s['col'])[:len(want)]
        if got != want: fail(f'line {ln} expected {w[2:]} got {s["map"]:02X} {s["row"]},{s["col"]}')
        emit('CHECK', f'{section}_{ln}')
    else:
        fail(f'line {ln} unknown step {op}')
    if os.environ.get('FFL3_STORYDENSE') and op in ('go', 'ride', 'face', 'a', 'shop', 'jump', 'settle'):
        pending_step[0] = f'L{ln}'                        # dense runs: emitted when a later step finds it free (no frames added)
emit('DONE', 'end')
if os.environ.get('STORY_STATE'):                         # debug: keep where the route ended
    with open(os.environ['STORY_STATE'], 'wb') as f: pb.save_state(f)
