"""Optimise approved Rinari art into apps/web/public/art/v2 (WebP, sized for the UI).

Sources: the owner-approved bank in ~/.claude/skills/rinari-promo/assets and the reviewed outputs of
the Codex jobs in artifacts/web-v2-art/*/out. Run with Pillow:  python apps/web/scripts/build-art.py
"""
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
BANK = Path.home() / '.claude/skills/rinari-promo/assets'
JOBS = ROOT / 'artifacts/web-v2-art'
OUT = ROOT / 'apps/web/public/art/v2'

# name -> (source, max box, quality)
BUSTS = {f'rinari/{n}': (BANK / 'v3' / f'exp-{n}.png', (720, 1080), 82) for n in
         ['focused', 'laugh', 'pout', 'pout-talk', 'proud', 'smug', 'smug-blink', 'smug-talk', 'surprised', 'surprised-blink']}
BUSTS |= {'rinari/shy': (JOBS / 'E/out/exp-shy.png', (720, 1080), 82), 'rinari/wink': (JOBS / 'E/out/exp-wink.png', (720, 1080), 82),
          'rinari/hero-cut': (BANK / 'v3/hero-cut.png', (900, 1350), 84)}
CHIBIS = {f'chibi/{n}': (BANK / folder / f'chibi-{n}.png', (420, 420), 84) for folder, names in {
    'v3': ['confetti', 'peek', 'point', 'stamp', 'tug', 'typing'], 'web': ['download', 'ledge', 'read', 'sleep', 'wave'],
    'mv': ['dance', 'glowsticks', 'sing'], 'discord': ['dj', 'party', 'wand', 'orbs']}.items() for n in names}
CHIBIS |= {f'chibi/{n}': (JOBS / job / f'out/chibi-{n}.png', (420, 420), 84) for job, names in
           {'C1': ['paint', 'clapper', 'cut'], 'C2': ['frames', 'tangled', 'offline']}.items() for n in names}
PLATES = {f'plates/{n}': (JOBS / job / f'out/plate-{n}.png', (1920, 1080), 80) for job, names in
          {'P1': ['entrance', 'home', 'image'], 'P2': ['edit', 'video', 'music', 'director']}.items() for n in names}


def save(name, source, box, quality, small=None, crop=True):
    if not source.exists():
        print('missing', source)
        return
    image = Image.open(source)
    image = image.convert('RGBA' if image.mode in ('RGBA', 'LA', 'P') else 'RGB')
    if image.mode == 'RGBA':  # clean Codex halos: faint alpha becomes fully transparent
        a = image.getchannel('A').point(lambda v: 0 if v < 40 else v)
        image.putalpha(a)
        if crop and image.getbbox():  # busts keep their shared framing so expressions crossfade aligned
            image = image.crop(image.getchannel('A').getbbox())
    target = OUT / f'{name}.webp'
    target.parent.mkdir(parents=True, exist_ok=True)
    copy = image.copy(); copy.thumbnail(box, Image.LANCZOS)
    copy.save(target, 'WEBP', quality=quality, method=6)
    sizes = [f'{target.stat().st_size // 1024} KB']
    if small:
        low = image.copy(); low.thumbnail(small, Image.LANCZOS)
        low_target = OUT / f'{name}-sm.webp'
        low.save(low_target, 'WEBP', quality=quality - 4, method=6)
        sizes.append(f'sm {low_target.stat().st_size // 1024} KB')
    print(f'{name}: {copy.size[0]}x{copy.size[1]} ' + ', '.join(sizes))


if __name__ == '__main__':
    only = set(sys.argv[1:])
    for group, small in ((BUSTS, None), (CHIBIS, None), (PLATES, (960, 540))):
        for name, (source, box, quality) in group.items():
            if not only or any(name.startswith(o) for o in only):
                save(name, source, box, quality, small, crop=not (name.startswith('rinari/') and name != 'rinari/hero-cut'))
