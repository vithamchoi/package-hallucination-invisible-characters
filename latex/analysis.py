#!/usr/bin/env python3
"""Analysis layer for the slopsquatting-exposure paper.

MEASURED  results/pilot/raw_model_outputs.jsonl -- 120 verbatim model answers
          results/pilot/package_validation.csv  -- one row per extracted name,
                                                   with its live PyPI verdict
          results/pilot/metrics.csv             -- the pilot's own summary
          results/pilot/run_meta.json           -- model, decoding, call count

DERIVED   Wilson intervals, a re-extraction of package names under a
          Unicode-aware pattern, and the difference between the two extractors.
          No number is simulated.

Imported by make_tables.py and make_figures.py so both read one code path.
"""
import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# The extractor the pilot actually used.
ASCII_RE = re.compile(r"pip install\s+([a-zA-Z0-9_\-\.]+)", re.I)
# The same rule with the character class widened to anything a shell would
# treat as one token, so a non-ASCII hyphen no longer truncates the name.
UNICODE_RE = re.compile(r"pip install\s+([^\s=<>\[\],;'\"]+)", re.I)

# Unicode dashes that look like a hyphen but are not U+002D.
DASHES = {0x2010: "U+2010 HYPHEN", 0x2011: "U+2011 NON-BREAKING HYPHEN",
          0x2012: "U+2012 FIGURE DASH", 0x2013: "U+2013 EN DASH",
          0x2014: "U+2014 EM DASH", 0x2212: "U+2212 MINUS SIGN"}

# PyPI verdicts for the names the two extractors disagree on. Queried live
# against pypi.org on 2026-09-05 and frozen here so the paper reproduces
# without network access; the query is one HTTP GET per name.
PYPI_RECHECK = {
    "pandas-profiling": True, "feature-tools": False, "category-encoders": True,
    "featuretools": True, "pandas": True, "feature": False, "category": True,
    "cleverscope": False,
}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def rule_of_three(n):
    return 3.0 / n


def normalise_dashes(s):
    return "".join("-" if ord(c) in DASHES else c for c in s)


class Data:
    def __init__(self, res):
        res = Path(res)
        self.raw = [json.loads(l) for l in
                    open(res / "pilot" / "raw_model_outputs.jsonl",
                         encoding="utf-8")]
        with open(res / "pilot" / "package_validation.csv", newline="",
                  encoding="utf-8") as f:
            self.rows = list(csv.DictReader(f))
        with open(res / "pilot" / "metrics.csv", newline="",
                  encoding="utf-8") as f:
            self.metrics = list(csv.DictReader(f))[0]
        self.meta = json.loads(
            (res / "pilot" / "run_meta.json").read_text(encoding="utf-8"))
        self.by_prompt = {r["prompt_id"]: r["raw"] for r in self.raw}

    # ------------------------------------------------------------- measured
    @property
    def n_prompts(self):
        return len(self.raw)

    @property
    def n_packages(self):
        return len(self.rows)

    @property
    def model(self):
        return self.meta["model"]

    @property
    def hallucinated(self):
        return [r for r in self.rows if r["hallucinated"] == "True"]

    @property
    def n_hallucinated(self):
        return len(self.hallucinated)

    @property
    def rate(self):
        return self.n_hallucinated / self.n_packages

    def distinct_packages(self):
        return len({r["package"] for r in self.rows})

    def distinct_outputs(self):
        return len({r["raw"] for r in self.raw})

    def packages_per_prompt(self):
        return Counter(Counter(r["prompt_id"] for r in self.rows).values())

    def prompts_with_hallucination(self):
        return len({r["prompt_id"] for r in self.hallucinated})

    def top_packages(self, k=12):
        return Counter(r["package"] for r in self.rows).most_common(k)

    def concentration(self, k=10):
        """Share of all suggestions taken by the k most-suggested names."""
        c = Counter(r["package"] for r in self.rows)
        return sum(n for _, n in c.most_common(k)) / self.n_packages

    # -------------------------------------------------- extractor validity
    def dash_audit(self):
        """Which outputs contain a non-ASCII dash, and how many."""
        hits = Counter()
        outputs = set()
        for r in self.raw:
            for ch in r["raw"]:
                if ord(ch) in DASHES:
                    hits[DASHES[ord(ch)]] += 1
                    outputs.add(r["prompt_id"])
        return hits, outputs

    def truncations(self):
        """Names the ASCII extractor cut short, with what they should have been."""
        out = []
        for r in self.raw:
            a = ASCII_RE.findall(r["raw"])
            u = [normalise_dashes(x).split("==")[0].strip(".,;")
                 for x in UNICODE_RE.findall(r["raw"])]
            for x, y in zip(a, u):
                if x != y and y.startswith(x):
                    out.append((r["prompt_id"], x, y,
                                PYPI_RECHECK.get(x), PYPI_RECHECK.get(y)))
        return out

    def corrected_counts(self):
        """Hallucination count after repairing the truncated extractions.

        A truncated capture is replaced by the name the model actually wrote,
        and that name's live PyPI verdict decides the outcome."""
        trunc = {(str(p), bad): (good, PYPI_RECHECK.get(good))
                 for p, bad, good, _, _ in self.truncations()}
        n = 0
        hall = []
        for r in self.rows:
            key = (r["prompt_id"], r["package"])
            if key in trunc:
                good, exists = trunc[key]
                n += 1
                if exists is False:
                    hall.append((r["prompt_id"], good))
            else:
                if r["hallucinated"] == "True":
                    hall.append((r["prompt_id"], r["package"]))
        return len(hall), self.n_packages, hall, n

    def counterfactual(self):
        """Range the reported rate could have taken had the coincidences in the
        truncated captures gone the other way. Lower end is the corrected
        count; upper end also counts the truncations whose short form happened
        to name a real package."""
        k, n, _, n_trunc = self.corrected_counts()
        return k / n, (k + len(self.coincidences()[0]) - 1) / n

    def coincidences(self):
        """Truncations whose verdict happened to match the untruncated name."""
        same, differ = [], []
        for p, bad, good, e_bad, e_good in self.truncations():
            (same if e_bad == e_good else differ).append((p, bad, good,
                                                          e_bad, e_good))
        return same, differ
