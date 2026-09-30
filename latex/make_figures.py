#!/usr/bin/env python3
"""Figures for the slopsquatting-exposure paper. Measured data only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np                                   # noqa: E402
import matplotlib.pyplot as plt                      # noqa: E402
import figstyle as F                                 # noqa: E402
from analysis import Data, wilson, rule_of_three     # noqa: E402

RES = Path(sys.argv[1] if len(sys.argv) > 1 else "../results")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "figures")
OUT.mkdir(parents=True, exist_ok=True)
D = Data(RES)
F.use_style()
W = 5.6

k, n, hall, _ = D.corrected_counts()
lo_cf, hi_cf = D.counterfactual()

# ===================================================== Fig 1: rate on a log axis
fig, ax = plt.subplots(figsize=(W, 2.5))
items = [
    ("Earlier pilot\n(n=5, planted names)", 0.40, None, F.C[1]),
    ("This measurement\n(n=353, extracted)", D.rate,
     wilson(D.n_hallucinated, D.n_packages), F.C[0]),
    ("Rule-of-three bound\nhad the count been 0", rule_of_three(D.n_packages),
     None, F.MUTED),
]
ys = np.arange(len(items))[::-1]
for y, (lab, v, iv, col) in zip(ys, items):
    ax.barh(y, 100 * v, height=0.5, color=col, edgecolor="white", linewidth=0.6)
    if iv:
        ax.plot([100 * iv[0], 100 * iv[1]], [y, y], color=F.INK, linewidth=1.0,
                zorder=5)
        ax.plot([100 * iv[0], 100 * iv[1]], [y, y], "|", color=F.INK,
                markersize=4, zorder=5)
    ax.text(100 * v * 1.25, y, f"{100 * v:.2f}%", va="center", ha="left",
            fontsize=7, color=col if col != F.MUTED else F.MUTED)
ax.set_yticks(ys)
ax.set_yticklabels([lab for lab, *_ in items], fontsize=7)
ax.set_xscale("log")
ax.set_xlim(0.1, 200)
ax.set_xticks([0.1, 1, 10, 100])
ax.set_xticklabels(["0.1", "1", "10", "100"])
ax.set_xlabel("Hallucinated-package rate (\\%, log scale)".replace("\\%", "%"))
ax.grid(axis="y", visible=False)
F.tidy(ax)
fig.tight_layout()
F.save(fig, OUT / "fig_rate.pdf")

# ============================================== Fig 2: extractor sensitivity
fig, ax = plt.subplots(figsize=(W, 2.3))
variants = [
    ("ASCII extractor\n(as run)", D.rate, F.C[0]),
    ("Unicode-aware\n(repaired)", k / n, F.C[2]),
    ("Worst case if the\ncoincidences differed", hi_cf, F.C[1]),
]
xs = np.arange(len(variants))
for x, (lab, v, col) in zip(xs, variants):
    lo, hi = wilson(round(v * n), n)
    ax.bar(x, 100 * v, width=0.5, color=col, edgecolor="white", linewidth=0.6)
    ax.plot([x, x], [100 * lo, 100 * hi], color=F.INK, linewidth=1.0, zorder=5)
    ax.text(x, 100 * hi + 0.08, f"{100 * v:.2f}%", ha="center", va="bottom",
            fontsize=7, color=col)
ax.set_xticks(xs)
ax.set_xticklabels([l for l, *_ in variants], fontsize=7)
ax.set_ylabel("Rate (\\%)".replace("\\%", "%"))
ax.set_ylim(0, 3.4)
ax.grid(axis="x", visible=False)
F.annotate_inside(ax, 1.0, 3.15,
                  f"one U+2011 character in {len(D.dash_audit()[1])} of "
                  f"{D.n_prompts} answers\ncorrupted {len(D.truncations())} of "
                  f"{D.n_packages} extractions",
                  ha="center", va="top", fontsize=6.8, color=F.MUTED)
F.tidy(ax)
fig.tight_layout()
F.save(fig, OUT / "fig_extractor.pdf")

# ================================================ Fig 3: suggestion concentration
fig, ax = plt.subplots(figsize=(W, 2.9))
top = D.top_packages(15)
exists = {r["package"]: r["exists"] == "True" for r in D.rows}
ys = np.arange(len(top))[::-1]
for y, (name, cnt) in zip(ys, top):
    col = F.C[0] if exists.get(name) else F.C[1]
    ax.barh(y, cnt, height=0.62, color=col, edgecolor="white", linewidth=0.5)
    ax.text(cnt + 0.3, y, str(cnt), va="center", ha="left", fontsize=6.6,
            color=F.MUTED)
ax.set_yticks(ys)
ax.set_yticklabels([t[0] for t in top], fontfamily="monospace", fontsize=7)
ax.set_xlabel("Times suggested across %d prompts" % D.n_prompts)
ax.set_xlim(0, max(c for _, c in top) * 1.18)
ax.grid(axis="y", visible=False)
handles = [plt.Rectangle((0, 0), 1, 1, color=F.C[0]),
           plt.Rectangle((0, 0), 1, 1, color=F.C[1])]
F.place_legend(ax, handles, ["exists on PyPI", "absent from PyPI"],
               allowed=["lower right", "center right"], fontsize=6.8,
               handlelength=1.1)
F.tidy(ax)
fig.tight_layout()
F.save(fig, OUT / "fig_top.pdf")

print("\nAll figures generated from:", RES.resolve())
