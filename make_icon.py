"""Draws rewind.ico and logo.png (same design as the logo in the UI). Run once: python make_icon.py"""
from PIL import Image, ImageDraw

def draw(size):
    S = 4 * size  # draw large, then downscale for smooth edges
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = Image.new("RGBA", (S, S))
    px = bg.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            px[x, y] = (int(18 + (10 - 18) * t), int(59 + (31 - 59) * t), int(134 + (74 - 134) * t), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 4, fill=255)
    im.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(im)
    u = S / 32
    w = int(2.6 * u)
    d.arc([8 * u, 8 * u, 24 * u, 24 * u], start=180, end=180 + 300, fill="white", width=w)
    d.polygon([(5.6 * u, 9.6 * u), (9.5 * u, 12.6 * u), (10.9 * u, 7.8 * u)], fill="white")
    d.polygon([(14 * u, 12.4 * u), (14 * u, 19.6 * u), (20 * u, 16 * u)], fill=(34, 193, 241))
    return im.resize((size, size), Image.LANCZOS)

big = draw(256)
big.save("rewind.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
big.save("logo.png")
print("wrote rewind.ico and logo.png")
