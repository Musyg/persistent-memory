"""Render an asciinema v2 cast to PNG frames plus an ffmpeg concat list.

Usage: render.py demo.cast outdir [end_marker]
"""
import json
import os
import sys

import pyte
from PIL import Image, ImageDraw, ImageFont

cast, out = sys.argv[1], sys.argv[2]
end_marker = sys.argv[3] if len(sys.argv) > 3 else None
os.makedirs(out, exist_ok=True)

lines = open(cast, encoding="utf-8").read().splitlines()
head = json.loads(lines[0])
events = [json.loads(x) for x in lines[1:] if x.strip()]
cols, rows = head["width"], head["height"]

FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
CW = round(FONT.getlength("M"))
CH = 23
PAD, BAR = 22, 34
W, H = PAD * 2 + CW * cols, BAR + PAD * 2 + CH * rows
BG, FG, DIM, ACC = (13, 17, 23), (230, 237, 243), (125, 133, 144), (47, 129, 247)

screen = pyte.Screen(cols, rows)
stream = pyte.Stream(screen)


def draw(path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, BAR], fill=(22, 27, 34))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 20, 11, 26 + i * 20, 23], fill=c)
    title = "persistent-memory-mcp 0.4.0a2 from PyPI"
    d.text(((W - FONT.getlength(title)) / 2, 7), title, font=FONT, fill=DIM)
    for y in range(rows):
        row = screen.buffer[y]
        text = "".join(row[x].data for x in range(cols)).rstrip()
        if not text:
            continue
        x0, y0 = PAD, BAR + PAD + y * CH
        if text.startswith(">>> ") or text.startswith("$ "):
            p = 4 if text.startswith(">>> ") else 2
            d.text((x0, y0), text[:p], font=FONT, fill=ACC)
            body = text[p:]
            code, sep, comment = body.partition("   # ")
            d.text((x0 + CW * p, y0), code, font=FONT, fill=FG)
            if sep:
                d.text((x0 + CW * (p + len(code)), y0), "   # " + comment, font=FONT, fill=DIM)
        else:
            d.text((x0, y0), text, font=FONT, fill=(158, 203, 255) if text[:1] in "['" else DIM)
    if not screen.cursor.hidden:
        cx, cy = PAD + screen.cursor.x * CW, BAR + PAD + screen.cursor.y * CH
        d.rectangle([cx, cy + 2, cx + CW - 1, cy + CH - 2], fill=(200, 210, 220))
    im.save(path)


frames = []  # (path, duration)
t_prev, n = 0.0, 0
acc = ""
for t, kind, data in events:
    if kind != "o":
        continue
    gap = t - t_prev
    if gap > 2.3:
        gap = 2.3           # cap long waits (pip download, pauses)
    elif gap < 0.12:
        gap *= 0.45         # quicker typing
    if frames:
        frames[-1][1] += gap
    t_prev = t
    if "\x04" in data:
        break
    stream.feed(data)
    acc += data
    path = os.path.join(out, f"f{n:05d}.png")
    draw(path)
    frames.append([path, 0.0])
    n += 1
    if end_marker and end_marker in acc and acc.rstrip().endswith(">>>"):
        break

frames[-1][1] = 4.0  # hold the last frame
with open(os.path.join(out, "list.txt"), "w") as f:
    for p, dur in frames:
        f.write(f"file '{os.path.basename(p)}'\nduration {max(dur, 0.02):.3f}\n")
    f.write(f"file '{os.path.basename(frames[-1][0])}'\n")
print(len(frames), "frames,", round(sum(d for _, d in frames), 1), "s,", W, "x", H)
