#!/usr/bin/env python3
"""LaTeX tables and macros for the slopsquatting-exposure paper."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis import Data, wilson, rule_of_three, PYPI_RECHECK  # noqa: E402

RES = Path(sys.argv[1] if len(sys.argv) > 1 else "../results")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "tables")
OUT.mkdir(parents=True, exist_ok=True)
D = Data(RES)


def write(name, body):
    (OUT / name).write_text(body.rstrip() + "\n", encoding="utf-8")
    print(f"wrote {OUT / name}")


def pc(x, d=2):
    return f"{100 * x:.{d}f}"


def ci(k, n):
    lo, hi = wilson(k, n)
    return f"[{pc(lo)}, {pc(hi)}]"


def tex(s):
    from analysis import DASHES
    out = []
    for ch in s:
        if ord(ch) in DASHES:
            # show the offending codepoint instead of the glyph: it is the
            # whole point of Section 5.2 and T1 cannot typeset it anyway
            out.append(r"{\footnotesize$\langle$U+%04X$\rangle$}" % ord(ch))
        else:
            out.append({"_": r"\_", "%": r"\%", "&": r"\&",
                        "#": r"\#"}.get(ch, ch))
    return "".join(out)


# ------------------------------------------------------------ Table: setup
m = D.meta
rows = [
    ("Model", r"\texttt{" + tex(m["model"]) + "}"),
    ("Provider", m["provider"].capitalize()),
    ("Decoding", r"$T=0$, \texttt{reasoning\_effort} = "
     + str(m.get("reasoning_effort")) + r", \texttt{max\_tokens} $\ge$ "
     + str(m.get("min_max_tokens"))),
    ("Prompts issued", f"{D.n_prompts} (12 task stems $\\times$ 10 style suffixes)"),
    ("Package names extracted", str(D.n_packages)),
    ("Distinct package names", str(D.distinct_packages())),
    ("Distinct model answers", f"{D.distinct_outputs()} of {D.n_prompts}"),
    ("Registry checked", r"\texttt{pypi.org} JSON API, one GET per name"),
    ("Empty-content retries", str(m.get("empty_content_retries", 0))),
    ("Wall-clock", f"{m['elapsed_seconds'] / 60:.1f} min at {m['rpm_limit']:.0f} req/min"),
]
write("tab_setup.tex", "\n".join(f"{a} & {b} \\\\" for a, b in rows))

# ------------------------------------------------------- Table: headline rate
k, n, hall, _ = D.corrected_counts()
lo_cf, hi_cf = D.counterfactual()
rows = [
    (r"Extracted names flagged as absent from PyPI",
     f"${D.n_hallucinated}/{D.n_packages}$", pc(D.rate), ci(D.n_hallucinated, D.n_packages)),
    (r"After repairing truncated extractions",
     f"${k}/{n}$", pc(k / n), ci(k, n)),
    (r"Prompts producing at least one absent name",
     f"${D.prompts_with_hallucination()}/{D.n_prompts}$",
     pc(D.prompts_with_hallucination() / D.n_prompts),
     ci(D.prompts_with_hallucination(), D.n_prompts)),
    (r"Rule-of-three bound had the count been zero",
     f"$0/{D.n_packages}$", pc(rule_of_three(D.n_packages)), "---"),
]
write("tab_rate.tex", "\n".join(" & ".join([a, b, c, d]) + r" \\" for a, b, c, d in rows))

# --------------------------------------------------- Table: the two positives
rows = []
for pid, name in hall:
    out = D.by_prompt[int(pid)]
    line = [l.strip() for l in out.split("\n") if name.split("-")[0] in l]
    rows.append(" & ".join([
        r"\texttt{" + tex(name) + "}",
        "no",
        r"\texttt{" + tex(line[0][:46] if line else "") + "}",
    ]) + r" \\")
write("tab_positives.tex", "\n".join(rows))

# ------------------------------------------------ Table: extractor disagreement
rows = []
for pid, bad, good, e_bad, e_good in D.truncations():
    rows.append(" & ".join([
        r"\texttt{" + tex(good) + "}",
        r"\texttt{" + tex(bad) + "}",
        "yes" if e_good else "\\textbf{no}",
        "yes" if e_bad else "\\textbf{no}",
        "same" if e_bad == e_good else r"\textbf{differs}",
    ]) + r" \\")
write("tab_extractor.tex", "\n".join(rows))

# -------------------------------------------------- Table: most-suggested names
rows = []
exists = {r["package"]: r["exists"] == "True" for r in D.rows}
for name, cnt in D.top_packages(12):
    rows.append(" & ".join([
        r"\texttt{" + tex(name) + "}", str(cnt),
        pc(cnt / D.n_packages, 1), "yes" if exists.get(name) else r"\textbf{no}",
    ]) + r" \\")
write("tab_top.tex", "\n".join(rows))

# ------------------------------------------------------------------- macros
h, dashout = D.dash_audit()
macros = [
    (r"\Nprompts", str(D.n_prompts)),
    (r"\Npkg", str(D.n_packages)),
    (r"\Ndistinctpkg", str(D.distinct_packages())),
    (r"\Ndistinctout", str(D.distinct_outputs())),
    (r"\Nhall", str(D.n_hallucinated)),
    (r"\Rate", pc(D.rate)),
    (r"\Ratelo", pc(wilson(D.n_hallucinated, D.n_packages)[0])),
    (r"\Ratehi", pc(wilson(D.n_hallucinated, D.n_packages)[1])),
    (r"\Ratecorr", pc(k / n)),
    (r"\Nhallcorr", str(k)),
    (r"\Ruleofthree", pc(rule_of_three(D.n_packages))),
    (r"\Model", tex(D.model).replace("/", "/\\allowbreak{}").replace("-", "-\\allowbreak{}")),
    (r"\Ntrunc", str(len(D.truncations()))),
    (r"\Ndashout", str(len(dashout))),
    (r"\Ndashchar", str(sum(h.values()))),
    (r"\Ncoin", str(len(D.coincidences()[0]))),
    (r"\CFlo", pc(lo_cf)),
    (r"\CFhi", pc(hi_cf)),
    (r"\Nhallprompts", str(D.prompts_with_hallucination())),
    (r"\Conc", pc(D.concentration(10), 0)),
    (r"\Elapsed", f"{m['elapsed_seconds'] / 60:.1f}"),
    (r"\Legacyrate", "40.00"),
    (r"\Legacyn", "5"),
]

# --- Bo sung: cac so lien quan den bien the cua bo trich xuat ---------------
import re as _re2
from collections import Counter as _C2

_OCC = _re2.compile(r"pip install\s+([^\s=<>,;'\"]+)", _re2.I)
_occ_tot = 0
_extras_ans = 0
for _r in D.raw:
    _toks = _OCC.findall(_r["raw"])
    _occ_tot += len(_toks)
    if any("[" in _x for _x in _toks):
        _extras_ans += 1
_per = _C2(r["prompt_id"] for r in D.rows)

# --- Bo sung: truy van lai PyPI sau mot khoang thoi gian ------------------
import datetime as _dt
import json as _json3
_rc = _json3.loads((RES / "recheck" / "pypi_recheck.json").read_text(encoding="utf-8"))
_t0 = _dt.datetime.fromisoformat(D.meta["finished_utc"].replace("Z", "+00:00"))
_t1 = _dt.datetime.fromisoformat(_rc["queried_utc"])
_gap = (_t1 - _t0).days
_orig = {r["package"]: (r["exists"] == "True") for r in D.rows}
_flips = [k for k, v in _rc["status"].items()
          if k in _orig and (v == 200) != _orig[k]]
_still = [k for k in ("feature", "cleverscope") if _rc["status"].get(k) == 404]

macros += [
    (r"\Recheckdays", str(_gap)),
    (r"\Recheckn", str(_rc["n_distinct"])),
    (r"\Recheckflips", str(len(_flips))),
    (r"\Recheckstill", str(len(_still))),
    (r"\Recheckdate", _t1.strftime("%d %B %Y")),
]

macros += [
    (r"\Nocc", str(_occ_tot)),
    (r"\Nextras", str(_extras_ans)),
    (r"\Nmaxper", str(max(_per.values()))),
    (r"\Ncapfive", "5"),
]
write("macros.tex", "\n".join(rf"\newcommand{{{a}}}{{{b}}}" for a, b in macros))
print("\nAll tables generated from:", RES.resolve())


# ===========================================================================
# Phan them: don vi phan tich nao? Lan nhac hay prompt?
#
# 353 lan nhac nam trong 120 prompt, nen chung khong doc lap. Duoi day tinh
# ICC mot chieu, he so thiet ke, co mau hieu dung, va khoang tin cay bootstrap
# theo cum, roi dat canh khoang Wilson muc lan nhac va muc prompt.
# Tat ca doc tu package_validation.csv, khong mo phong.
# ===========================================================================
import collections as _c2
import math as _m2
import random as _r2

_g = _c2.OrderedDict()
for _r in D.rows:
    _g.setdefault(_r["prompt_id"], []).append(_r)

_m = len(_g)
_n = len(D.rows)
_k = sum(1 for _r in D.rows if _r["hallucinated"] == "True")
_sizes = [len(v) for v in _g.values()]
_nbar = _n / _m

# ICC ANOVA mot chieu tren bien nhi phan
_pbar = _k / _n
_ssb = sum(len(v) * ((sum(1 for r in v if r["hallucinated"] == "True") / len(v))
                     - _pbar) ** 2 for v in _g.values())
_ssw = 0.0
for _v in _g.values():
    _pv = sum(1 for r in _v if r["hallucinated"] == "True") / len(_v)
    for _r in _v:
        _ssw += ((1 if _r["hallucinated"] == "True" else 0) - _pv) ** 2
_msb = _ssb / (_m - 1)
_msw = _ssw / (_n - _m)
_n0 = (_n - sum(s * s for s in _sizes) / _n) / (_m - 1)
_icc = ((_msb - _msw) / (_msb + (_n0 - 1) * _msw)) if (_msb + (_n0 - 1) * _msw) else 0.0
_deff = 1 + (_nbar - 1) * _icc
_ess = _n / _deff

# bootstrap theo cum: lay lai prompt, khong lay lai lan nhac
_r2.seed(42)
_B = 20000
_keys = list(_g.keys())
_est = []
for _ in range(_B):
    _s = [_g[_r2.choice(_keys)] for _ in range(_m)]
    _fl = [r for v in _s for r in v]
    _est.append(sum(1 for r in _fl if r["hallucinated"] == "True") / len(_fl))
_est.sort()
_cb_lo, _cb_hi = _est[int(0.025 * _B)], _est[int(0.975 * _B)]

# muc prompt
_hp = sum(1 for v in _g.values() if any(r["hallucinated"] == "True" for r in v))
_pw_lo, _pw_hi = wilson(_hp, _m)
_mw_lo, _mw_hi = wilson(_k, _n)

# vi tri cua goi ao trong danh sach cua prompt do
_pos = []
for _pid, _v in _g.items():
    for _i, _r in enumerate(_v, 1):
        if _r["hallucinated"] == "True":
            _pos.append((_pid, _r["package"], _i, len(_v)))

_rows_unit = [
    r"Mention & %d & %d & %s & %s \\" % (_k, _n, pc(_k / _n), ci(_k, _n)),
    r"Mention, clustered & %d & %d & %s & [%s, %s] \\"
    % (_k, _n, pc(_k / _n), pc(_cb_lo), pc(_cb_hi)),
    r"Prompt & %d & %d & %s & %s \\" % (_hp, _m, pc(_hp / _m), ci(_hp, _m)),
]
write("tab_unit.tex", "\n".join(_rows_unit))

_rows_pos = [r"%s & \texttt{%s} & %d of %d \\" % (p, pk.replace("_", r"\_"), i, t)
             for p, pk, i, t in _pos]
write("tab_pos.tex", "\n".join(_rows_pos))

_extra = [
    (r"\UNprompt", str(_m)),
    (r"\UNbar", "%.2f" % _nbar),
    (r"\UIcc", "%.4f" % _icc),
    (r"\UDeff", "%.4f" % _deff),
    (r"\UEss", "%.1f" % _ess),
    (r"\UBoot", "%d" % _B),
    (r"\UCbLo", pc(_cb_lo)),
    (r"\UCbHi", pc(_cb_hi)),
    (r"\UMwLo", pc(_mw_lo)),
    (r"\UMwHi", pc(_mw_hi)),
    (r"\UPrompthit", str(_hp)),
    (r"\UPromptrate", pc(_hp / _m)),
    (r"\UPwLo", pc(_pw_lo)),
    (r"\UPwHi", pc(_pw_hi)),
    (r"\URatio", "%.1f" % ((_hp / _m) / (_k / _n))),
    (r"\UClusterThree", str(sum(1 for s in _sizes if s == 3))),
    (r"\UClusterTwo", str(sum(1 for s in _sizes if s == 2))),
    (r"\UClusterOne", str(sum(1 for s in _sizes if s == 1))),
    (r"\UPosBoth", str(_pos[0][2]) if len({p[2] for p in _pos}) == 1 else "varied"),
]
with open(OUT / "macros.tex", "a", encoding="utf-8") as _f:
    _f.write("\n%% --- don vi phan tich: lan nhac hay prompt ---\n")
    for _a, _b in _extra:
        _f.write(rf"\newcommand{{{_a}}}{{{_b}}}" + "\n")
print(f"wrote {len(_extra)} macro don vi phan tich + 2 bang")


# ===========================================================================
# Phan them 2: hinh dang phan bo ten goi.
# "Tap trung" la mot tu; duoi day la so. Doc tu package_validation.csv.
# ===========================================================================
_cnt = _c2.Counter(r["package"] for r in D.rows)
_srt = _cnt.most_common()
_ntot = len(D.rows)
_nd = len(_cnt)
_cum, _cov = 0, {}
for _i, (_kk, _vv) in enumerate(_srt, 1):
    _cum += _vv
    _cov[_i] = _cum / _ntot

_rows_cov = []
for _k in (1, 5, 10, 15, 20, 26, 30, 40, _nd):
    if _k <= _nd:
        _rows_cov.append(r"%d & %d & %s \\"
                         % (_k, sum(v for _, v in _srt[:_k]), pc(_cov[_k], 1)))
write("tab_cover.tex", "\n".join(_rows_cov))

_ones = [_kk for _kk, _vv in _cnt.items() if _vv == 1]
_ps = [_vv / _ntot for _, _vv in _srt]
_H = -sum(_p * _m2.log(_p) for _p in _ps)
_Hmax = _m2.log(_nd)

_extra2 = [
    (r"\SOnes", str(len(_ones))),
    (r"\SOnesPctNames", pc(len(_ones) / _nd, 1)),
    (r"\SOnesPctMentions", pc(len(_ones) / _ntot)),
    (r"\SShannon", "%.4f" % _H),
    (r"\SShannonMax", "%.4f" % _Hmax),
    (r"\SEven", pc(_H / _Hmax, 1)),
    (r"\SEffNames", "%.1f" % _m2.exp(_H)),
    (r"\SHalfAt", str(next(k for k in sorted(_cov) if _cov[k] >= 0.5))),
    (r"\SNinetyAt", str(next(k for k in sorted(_cov) if _cov[k] >= 0.9))),
    (r"\SPerName", pc(1 / _ntot)),
    (r"\SHallMentions", str(sum(_cnt[k] for k in _cnt
                                if any(r["package"] == k and r["hallucinated"] == "True"
                                       for r in D.rows)))),
]
with open(OUT / "macros.tex", "a", encoding="utf-8") as _f:
    _f.write("\n%% --- hinh dang phan bo ten goi ---\n")
    for _a, _b in _extra2:
        _f.write(rf"\newcommand{{{_a}}}{{{_b}}}" + "\n")
print(f"wrote {len(_extra2)} macro phan bo + 1 bang")
