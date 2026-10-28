"""Figures for 'How it works' made from the synthetic demo plot.

Usage: python make_figs.py <results folder of one scan, e.g. wyniki/demo_plot>
The scan is made with tree_segmenter_tool/90_make_test_forest.py --drzew 28 --nazwa demo_plot.
"""
import sys
import numpy as np, pandas as pd, laspy, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from pathlib import Path
W = Path(sys.argv[1]); O = Path(__file__).resolve().parent / "fig"
N = W.name
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
rng = np.random.default_rng(1)

seg = laspy.read(W / f"02_CHMURY/{N}_segmenty.laz")
X, Y, Z = np.asarray(seg.x), np.asarray(seg.y), np.asarray(seg.z)
H = np.asarray(seg.wys_nad_grunt); T = np.asarray(seg.treeID_pred)
okr = pd.read_csv(W / f"03_TABELE/{N}_okregi.csv")
pien = pd.read_csv(W / f"03_TABELE/{N}_pien_okregi.csv")
rap = pd.read_csv(W / f"03_TABELE/{N}_drzewa_raport.csv")

# 1 terrain + normalisation
band = np.abs(Y - 15) < 1.0
s = rng.choice(np.where(band)[0], min(60000, band.sum()), replace=False)
fig, ax = plt.subplots(2, 1, figsize=(10, 5.2), sharex=True)
ax[0].scatter(X[s], Z[s], s=0.3, c="#4a7a4a", lw=0)
g = s[H[s] < 0.05]; o = np.argsort(X[g])
ax[0].plot(X[g][o], Z[g][o] - H[g][o], color="#8a5a2b", lw=2, label="terrain model (DTM)")
ax[0].set_ylabel("z from the scanner [m]"); ax[0].legend(loc="upper right")
ax[1].scatter(X[s], H[s], s=0.3, c="#4a7a4a", lw=0)
ax[1].axhline(1.3, color="#c62828", lw=1.2, ls="--"); ax[1].text(0.3, 1.8, "1.3 m (DBH)", color="#c62828")
ax[1].set_ylabel("height above ground [m]"); ax[1].set_xlabel("x [m]")
fig.tight_layout(); fig.savefig(O / "hw_terrain.png", dpi=150); plt.close(fig)

# 2 stem detection in a slice
sl = (H > 1.75) & (H < 2.0)
c = okr[(okr.wysokosc_m > 1.7) & (okr.wysokosc_m < 2.05)]
fig, ax = plt.subplots(1, 2, figsize=(10, 5))
ax[0].scatter(X[sl], Y[sl], s=0.6, c="#555", lw=0); ax[0].set_title("slice 1.75–2.0 m above ground")
ax[1].scatter(X[sl], Y[sl], s=0.6, c="#bbb", lw=0)
for _, r in c.iterrows():
    ax[1].add_patch(plt.Circle((r.srodek_x, r.srodek_y), r.promien_m, fill=False, color="#c62828", lw=1.4))
ax[1].set_title(f"circles that passed the tests ({len(c)})")
for a in ax: a.set_aspect("equal"); a.set_xlabel("x [m]"); a.set_ylabel("y [m]")
fig.tight_layout(); fig.savefig(O / "hw_slice.png", dpi=150); plt.close(fig)

# 3 circle fit on one tree
nr = 1; r0 = pien[(pien.treeID == nr)]; r13 = r0.iloc[(r0.wysokosc_m - 1.3).abs().argmin()]
m = (T == nr) & (np.abs(H - 1.3) < 0.05)
dx, dy = (X[m] - r13.srodek_x) * 100, (Y[m] - r13.srodek_y) * 100; R = r13.srednica_m * 50
fig, ax = plt.subplots(1, 2, figsize=(10, 4.6))
ax[0].scatter(dx, dy, s=4, c="#6d4c2f"); ax[0].add_patch(plt.Circle((0, 0), R, fill=False, color="#c62828", lw=1.5))
ang = np.arctan2(dy, dx); d = np.hypot(dx, dy)
for i in range(0, len(dx), 3):
    ax[0].plot([dx[i], R * np.cos(ang[i])], [dy[i], R * np.sin(ang[i])], color="#1565c0", lw=0.6)
ax[0].set_aspect("equal"); ax[0].set_title(f"tree {nr} at 1.3 m: DBH {2*R:.1f} cm"); ax[0].set_xlabel("[cm]"); ax[0].set_ylabel("[cm]")
ax[1].hist(d - R, bins=30, color="#1565c0"); ax[1].set_title("distance of the points from the circle")
ax[1].set_xlabel("residual [cm]"); ax[1].set_ylabel("points")
fig.tight_layout(); fig.savefig(O / "hw_circle.png", dpi=150); plt.close(fig)

# 4 segmentation top view
s = rng.choice(np.where(H > 0.5)[0], 150000, replace=False)
cm = plt.get_cmap("tab20"); col = np.where(T[s] > 0, T[s] % 20, -1)
fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(X[s][col < 0], Y[s][col < 0], s=0.2, c="#ccc", lw=0)
ax.scatter(X[s][col >= 0], Y[s][col >= 0], s=0.2, c=cm(col[col >= 0]), lw=0)
for _, r in rap.iterrows(): ax.text(r.x, r.y, str(int(r.nr)), fontsize=8, ha="center", va="center", weight="bold")
ax.set_aspect("equal"); ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]"); ax.set_title("every tree in its own colour (top view)")
fig.tight_layout(); fig.savefig(O / "hw_segmentation.png", dpi=150); plt.close(fig)

# 5 taper
nr = 4; r0 = pien[pien.treeID == nr]; m = T == nr
fig, ax = plt.subplots(1, 2, figsize=(10, 5.4), gridspec_kw={"width_ratios": [1, 1.4]})
ss = np.where(m)[0][::4]
ax[0].scatter(X[ss] - r0.srodek_x.iloc[0], H[ss], s=0.3, c="#7a9a7a", lw=0)
for _, r in r0.iterrows():
    col = "#1565c0" if r.zrodlo != "pomiar" else "#c62828"
    ax[0].plot([r.srodek_x - r0.srodek_x.iloc[0] - r.srednica_m / 2, r.srodek_x - r0.srodek_x.iloc[0] + r.srednica_m / 2], [r.wysokosc_m] * 2, color=col, lw=1)
ax[0].set_xlim(-2, 2); ax[0].set_xlabel("x [m]"); ax[0].set_ylabel("height above ground [m]"); ax[0].set_title(f"tree {nr}: stem circles every 20 cm")
ax[1].plot(r0.srednica_m * 100, r0.wysokosc_m, ".", color="#c62828", ms=4, label="measured")
ax[1].plot(r0.srednica_wygladzona_m * 100, r0.wysokosc_m, color="k", lw=1.2, label="smoothed")
ax[1].set_xlabel("stem diameter [cm]"); ax[1].set_ylabel("height [m]"); ax[1].set_title("taper curve"); ax[1].legend()
fig.tight_layout(); fig.savefig(O / "hw_taper.png", dpi=150); plt.close(fig)

# 6 height curve
d, h = rap.d13.values, rap.h.values
f = lambda d, a, b: 1.3 + d**2 / (a + b * d)**2
p, _ = curve_fit(f, d, h, p0=(1, 0.2), maxfev=10000)
xx = np.linspace(d.min() * 0.8, d.max() * 1.1, 100)
fig, ax = plt.subplots(figsize=(7, 4.6))
ax.scatter(d, h, c="#2e7d32", s=22, label="trees"); ax.plot(xx, f(xx, *p), "k", label="Näslund curve h = 1.3 + d² / (a + b·d)²")
ax.set_xlabel("DBH [cm]"); ax.set_ylabel("height [m]"); ax.legend(); ax.set_title("height–diameter curve of the plot")
fig.tight_layout(); fig.savefig(O / "hw_height_curve.png", dpi=150); plt.close(fig)

# 7 hollow stem vs shrub (illustration)
fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.8))
def ring(n, r, arc, noise): a = rng.uniform(0, np.radians(arc), n); rr = r + rng.normal(0, noise, n); return rr*np.cos(a), rr*np.sin(a)
x, y = ring(260, 18, 360, 0.6); ax[0].scatter(x, y, s=4, c="#6d4c2f"); ax[0].set_title("stem: points only on the bark\n0–2 % inside")
x, y = ring(160, 22, 150, 0.8); ax[1].scatter(x, y, s=4, c="#6d4c2f"); ax[1].set_title("stem seen from one side:\nan arc, still empty inside")
x = rng.normal(0, 14, 450); y = rng.normal(0, 14, 450); ax[2].scatter(x, y, s=4, c="#558b2f"); ax[2].set_title("shrub / branch cluster:\n20–50 % inside")
for a in ax:
    a.add_patch(plt.Circle((0, 0), 20, fill=False, color="#c62828", lw=1.2)); a.add_patch(plt.Circle((0, 0), 14, fill=False, color="#c62828", lw=0.8, ls="--"))
    a.set_aspect("equal"); a.set_xlim(-35, 35); a.set_ylim(-35, 35); a.set_xticks([]); a.set_yticks([])

fig.tight_layout(); fig.savefig(O / "hw_hollow.png", dpi=150); plt.close(fig)
print("ok")
