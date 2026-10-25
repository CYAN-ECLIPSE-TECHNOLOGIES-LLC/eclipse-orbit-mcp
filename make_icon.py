#!/usr/bin/env python3
"""Generate icon-512.png — brand §6: eclipse motif on navy (#0d1b2a),
one per-product glyph. Orbit's glyph is an orbit ellipse with a
satellite node circling the eclipse core — the wrap around the
vendor's sun — inside the gradient eclipse ring. PIL only;
deterministic."""
from PIL import Image, ImageDraw

S = 512
NAVY = (13, 27, 42, 255)
STOPS = [(15, 246, 247), (0, 212, 255), (123, 44, 191)]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


def grad(t):
    return lerp(STOPS[0], STOPS[1], t * 2) if t < 0.5 else \
        lerp(STOPS[1], STOPS[2], (t - 0.5) * 2)


def main():
    img = Image.new("RGBA", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    ring = [54, 54, 458, 458]
    for i in range(72):
        t = i / 72
        d.arc(ring, start=i * 5, end=i * 5 + 6, fill=grad(t), width=13)
    d.ellipse([126, 126, 386, 386], fill=NAVY)
    # The core (the vendor's sun, eclipsed).
    d.ellipse([216, 216, 296, 296], fill=grad(0.15))
    d.ellipse([232, 206, 302, 286], fill=NAVY)
    # The orbit ellipse + satellite node (the wrap).
    d.ellipse([156, 196, 356, 316], outline=grad(0.55), width=7)
    d.ellipse([330, 226, 358, 254], fill=grad(0.85))
    img.save("icon-512.png")
    print("wrote icon-512.png", img.size, img.mode)


if __name__ == "__main__":
    main()
