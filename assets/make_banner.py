#!/usr/bin/env python3
"""Draw assets/banner.png for the README (matplotlib only).  python assets/make_banner.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

NAVY, NAVY2 = "#141c3a", "#222b67"
TEAL, ORANGE, RED, GREEN, CREAM, INK = "#3da4b3", "#f39c12", "#e0514f", "#3fae6a", "#f9e2ab", "#3b3f52"
W, H = 9.0, 2.7  # inches @ 200 dpi -> 1800 x 540
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
R = fig.canvas.get_renderer()


def width_in(t):
    return t.get_window_extent(R).width / fig.dpi


# background: diagonal navy gradient + faint dot grid
gx, gy = np.meshgrid(np.linspace(0, 1, 450), np.linspace(0, 1, 135))
cmap = matplotlib.colors.LinearSegmentedColormap.from_list("bg", [NAVY, NAVY2])
ax.imshow(0.55 * gx + 0.45 * (1 - gy), extent=(0, W, 0, H), cmap=cmap, aspect="auto", zorder=0)
xs, ys = np.meshgrid(np.arange(0.15, W, 0.22), np.arange(0.15, H, 0.22))
ax.scatter(xs, ys, s=1.2, color="white", alpha=0.10, zorder=1)

# ---------------- left: title block
ax.text(0.45, 2.22, "A  CURSOR  AGENT  SKILL", color=ORANGE, fontsize=8.5, fontweight="bold", va="center", zorder=5)
t1 = ax.text(0.43, 1.74, "Cite", color="white", fontsize=30, fontweight="bold", va="center", zorder=5)
ax.text(0.43 + width_in(t1) + 0.02, 1.74, "Witness", color=ORANGE, fontsize=30, fontweight="bold", va="center", zorder=5)
ax.text(0.45, 1.24, "Every citation has a witness.", color="white", fontsize=12.5, va="center", zorder=5)
ax.text(0.45, 0.94, "Every field from a retrieved record — never from memory.", color=CREAM, fontsize=10.5, va="center", zorder=5, style="italic")
x = 0.45
for lab in ["arXiv API", "Crossref", "DBLP", "proceedings index"]:
    t = ax.text(x + 0.09, 0.46, lab, color="white", fontsize=7.6, va="center", ha="left", zorder=6)
    w = width_in(t) + 0.18
    ax.add_patch(FancyBboxPatch((x, 0.34), w, 0.24, boxstyle="round,pad=0,rounding_size=0.12", fc="none", ec=TEAL, lw=1.0, zorder=5))
    x += w + 0.09

# ---------------- right: a bib card being audited
cx, cy, cw, ch = 4.95, 0.30, 3.70, 2.08
ax.add_patch(FancyBboxPatch((cx + 0.06, cy - 0.06), cw, ch, boxstyle="round,pad=0,rounding_size=0.10", fc="black", alpha=0.35, ec="none", zorder=3))
ax.add_patch(FancyBboxPatch((cx, cy), cw, ch, boxstyle="round,pad=0,rounding_size=0.10", fc="#fbfbfd", ec="none", zorder=4))
bar_h = 0.30
ax.add_patch(FancyBboxPatch((cx, cy + ch - bar_h), cw, bar_h, boxstyle="round,pad=0,rounding_size=0.10", fc="#e9ecf5", ec="none", zorder=4))
ax.add_patch(plt.Rectangle((cx, cy + ch - bar_h), cw, 0.12, fc="#e9ecf5", ec="none", zorder=4))
for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
    ax.add_patch(plt.Circle((cx + 0.20 + i * 0.17, cy + ch - bar_h / 2), 0.045, fc=c, ec="none", zorder=5))
ax.text(cx + 0.72, cy + ch - bar_h / 2, "verify_bib.py  demo.bib", color="#5c6480", fontsize=7.4, va="center", zorder=5,
        family="DejaVu Sans Mono")
# verdict stamp in the title bar
sw = 0.98
ax.add_patch(FancyBboxPatch((cx + cw - sw - 0.12, cy + ch - bar_h + 0.05), sw, 0.20, boxstyle="round,pad=0,rounding_size=0.05",
                            fc=RED, ec="none", zorder=6))
ax.text(cx + cw - sw / 2 - 0.12, cy + ch - bar_h / 2, "FAIL · 2 entries", color="white", fontsize=7.4, fontweight="bold",
        ha="center", va="center", zorder=7)

mono = dict(family="DejaVu Sans Mono", fontsize=7.2, va="center", zorder=6)
lines = [  # (code, code colour, tag colour, tag, strike) -- the entries of examples/demo.bib
    ("@inproceedings{resnet,", INK, None, None, False),
    ("  title  = {Deep Residual ...},", INK, GREEN, "✓ arXiv 1512.03385", False),
    ("  author = {He, K. and Zhang, X. and", INK, None, None, False),
    ("     Ren, S., Sun, J., Smith, J.},", RED, RED, "✗ Smith not in record", True),
    ("  booktitle = {CVPR},", INK, GREEN, "✓ Crossref: CVPR 2016", False),
    ("}", INK, None, None, False),
    ("@inproceedings{dit,", INK, None, None, False),
    ("  booktitle = {NeurIPS},", RED, RED, "✗ record says ICCV 2023", True),
]
y = cy + ch - bar_h - 0.22
for code, col, tagc, tag, strike in lines:
    t = ax.text(cx + 0.16, y, code, color=col, **mono)
    if strike:
        ax.plot([cx + 0.16, cx + 0.16 + width_in(t)], [y, y], color=RED, lw=1.0, alpha=0.7, zorder=7)
    if tag:
        ax.text(cx + cw - 0.14, y, tag, color=tagc, fontsize=6.8, ha="right", va="center", zorder=6, fontweight="bold")
    y -= 0.205

out = Path(__file__).with_name("banner.png")
fig.savefig(out, dpi=200)
print("->", out)
