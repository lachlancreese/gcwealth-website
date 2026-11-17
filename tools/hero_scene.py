#!/usr/bin/env python3
"""Draw the homepage hero: the Gold Coast skyline at sunset, seen from the water, in brand colours.

    python3 tools/hero_scene.py      # writes pages/partials/hero-coast.html, then run build.py

Everything is plain SVG shapes, animated with CSS in site.css (.coast ...): the sun settles, window lights come on,
the water moves. Visitors who ask for reduced motion see the finished still. A fixed seed keeps the drawing the same
on every build, so change SEED to try a different skyline.
"""
import math, pathlib, random

SEED = 11
W, H = 800, 600
HORIZON = 432          # foot of the towers (the beachfront)
WATER = 448            # where the ocean starts
SUN = (566, 352, 54)   # x, y, radius: low, sitting in a gap between towers
OUT = pathlib.Path(__file__).resolve().parent.parent / "pages" / "partials" / "hero-coast.html"

# Towers along the beachfront: (left x, width, height, top style). The tall slim one with a spire is the landmark.
TOWERS = [
    (30, 36, 70, "flat"), (68, 28, 112, "step"), (98, 42, 92, "flat"), (142, 30, 150, "crown"),
    (174, 46, 120, "flat"), (222, 34, 172, "step"), (258, 42, 132, "flat"), (302, 32, 104, "round"),
    (336, 38, 156, "flat"), (378, 28, 214, "spire"), (410, 44, 160, "step"), (458, 32, 118, "flat"),
    (492, 28, 84, "round"), (524, 34, 62, "flat"), (612, 30, 70, "flat"), (644, 44, 168, "crown"),
    (690, 36, 124, "step"), (728, 42, 96, "flat"), (772, 30, 76, "flat"),
]


def f(n):
    return f"{n:.1f}".rstrip("0").rstrip(".")


def wave_path(y, amp, period, x0=-400, x1=1200):
    pts = []
    x = x0
    while x <= x1:
        pts.append(f"{f(x)},{f(y + amp * math.sin(2 * math.pi * x / period))}")
        x += period / 8
    return "M" + " L".join(pts)


def main():
    rnd = random.Random(SEED)
    out = []
    a = out.append
    a(f'<svg class="coast" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">')
    a("""<defs>
  <linearGradient id="c-sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0E3242"/><stop offset=".34" stop-color="#1F5878"/><stop offset=".58" stop-color="#4E8DB0"/>
    <stop offset=".74" stop-color="#C9B49A"/><stop offset=".86" stop-color="#EDC48E"/><stop offset="1" stop-color="#F6DDB4"/>
  </linearGradient>
  <radialGradient id="c-glow"><stop offset="0" stop-color="#FCE3B4" stop-opacity=".95"/><stop offset=".35" stop-color="#F3C584" stop-opacity=".55"/><stop offset="1" stop-color="#F0C48C" stop-opacity="0"/></radialGradient>
  <radialGradient id="c-sun"><stop offset="0" stop-color="#FFF6E4"/><stop offset=".7" stop-color="#FBDDAA"/><stop offset="1" stop-color="#F3C487"/></radialGradient>
  <linearGradient id="c-tower" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#123A4C"/><stop offset="1" stop-color="#0A2532"/></linearGradient>
  <linearGradient id="c-sea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A6A88"/><stop offset=".35" stop-color="#1A5068"/><stop offset="1" stop-color="#0B2B3A"/></linearGradient>
</defs>""")
    a(f'<rect width="{W}" height="{WATER}" fill="url(#c-sky)"/>')
    sx, sy, sr = SUN
    a(f'<g class="sun-group"><circle class="glow" cx="{sx}" cy="{sy}" r="300" fill="url(#c-glow)"/>'
      f'<circle class="sun" cx="{sx}" cy="{sy}" r="{sr}" fill="url(#c-sun)"/></g>')

    # Two birds, high and drifting.
    a('<g class="birds" fill="none" stroke="#0E3242" stroke-width="1.6" stroke-linecap="round" opacity=".55">'
      '<path d="M210 168 q6 -6 12 0 q6 -6 12 0"/><path d="M246 186 q4 -4 8 0 q4 -4 8 0"/></g>')

    # Hinterland hills, soft behind the towers.
    hill = "M0 " + f(HORIZON - 26) + " " + " ".join(
        f"L{x} {f(HORIZON - 26 - 14 * math.sin(x / 95) - 8 * math.sin(x / 37 + 1))}" for x in range(0, W + 1, 20)) + f" L{W} {HORIZON} L0 {HORIZON} Z"
    a(f'<path d="{hill}" fill="#3D7895" opacity=".55"/>')

    # Lower towers in the haze behind the beachfront.
    back = []
    x = 10
    while x < W - 10:
        w = rnd.randint(18, 34)
        h = rnd.randint(30, 80)
        back.append(f'<rect x="{x}" y="{HORIZON - h}" width="{w}" height="{h}"/>')
        x += w + rnd.randint(2, 10)
    a(f'<g fill="#2A5D75" opacity=".7">{"".join(back)}</g>')

    # Beachfront towers, with lit windows.
    towers, lights = [], []
    for (x, w, h, top) in TOWERS:
        y = HORIZON - h
        towers.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>')
        if top == "step":
            towers.append(f'<rect x="{x + w * .2:.1f}" y="{y - 12}" width="{w * .6:.1f}" height="13"/>')
        elif top == "crown":
            towers.append(f'<rect x="{x + w * .3:.1f}" y="{y - 18}" width="{w * .4:.1f}" height="19"/>'
                          f'<rect x="{x + w * .47:.1f}" y="{y - 34}" width="{w * .06:.1f}" height="17"/>')
        elif top == "round":
            towers.append(f'<path d="M{x} {y + 1} Q{x + w / 2} {y - 22} {x + w} {y + 1} Z"/>')
        elif top == "spire":
            towers.append(f'<path d="M{x + 3} {y + 1} L{x + w / 2} {y - 34} L{x + w - 3} {y + 1} Z"/>'
                          f'<rect x="{x + w / 2 - 1:.1f}" y="{y - 92}" width="2" height="60"/>')
        cols = max(2, int((w - 6) // 7))
        rows = int((h - 14) // 9)
        for r in range(rows):
            for c in range(cols):
                if rnd.random() < 0.13:
                    wx = x + 4 + c * 7
                    wy = y + 8 + r * 9
                    warm = rnd.random() < 0.82
                    delay = 0.8 + rnd.random() * 2.6
                    twinkle = rnd.random() < 0.18
                    cls = "lit tw" if twinkle else "lit"
                    style = f"--d:{delay:.2f}s" + (f";--t:{rnd.uniform(3.5, 8):.1f}s" if twinkle else "")
                    lights.append(f'<rect class="{cls}" style="{style}" x="{wx}" y="{wy}" width="3" height="4"'
                                  f'{"" if warm else " fill=\"#DCEBF2\""}/>')
    a(f'<g fill="url(#c-tower)">{"".join(towers)}</g>')
    a(f'<g fill="#F7D9A2">{"".join(lights)}</g>')

    # Beach, then the ocean with the sun's reflection and moving swell.
    a(f'<rect y="{HORIZON}" width="{W}" height="{WATER - HORIZON}" fill="#173E50"/>')
    a(f'<rect y="{WATER}" width="{W}" height="{H - WATER}" fill="url(#c-sea)"/>')
    refl = []
    yy = WATER + 4
    i = 0
    while yy < H:
        span = 18 + (yy - WATER) * 0.55
        jitter = rnd.uniform(-10, 10)
        refl.append(f'<rect class="ref" style="--d:{rnd.uniform(0, 2.5):.2f}s;--t:{rnd.uniform(1.6, 3.2):.1f}s" '
                    f'x="{f(sx - span / 2 + jitter)}" y="{f(yy)}" width="{f(span * rnd.uniform(.55, 1))}" height="2" rx="1"/>')
        yy += 6 + i * 0.35
        i += 1
    a(f'<g fill="#F6CF96" opacity=".75">{"".join(refl)}</g>')
    for (y, amp, period, op, secs, width) in [(468, 2.5, 160, .22, 26, 1.4), (500, 3.5, 200, .26, 21, 1.6),
                                             (538, 4.5, 240, .3, 17, 1.8), (578, 5.5, 280, .34, 13, 2)]:
        a(f'<path class="wave" style="--t:{secs}s;--p:-{period}px" d="{wave_path(y, amp, period)}" fill="none" '
          f'stroke="#EAF2F6" stroke-opacity="{op}" stroke-width="{width}" stroke-linecap="round"/>')
    a("</svg>")
    OUT.write_text("\n".join(out) + "\n")
    print(OUT, f"{OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
