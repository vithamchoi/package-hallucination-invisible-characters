"""Trich xuat va kiem tra lai bai 07 tu obscure_raw.jsonl -- KHONG goi LLM.

Chi can mang toi pypi.org. Dung khi da co cau tra loi tho roi nhung bo trich
xuat bi sai: khong phai chay lai model.

Ghi: results/obscure/obscure_validation.json (ghi de ban cu)
"""
import json, os, re, sys, time, unicodedata
from pathlib import Path
import urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fix_obscure_stems import extract, norm          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "obscure"
RAW = OUT / "obscure_raw.jsonl"
VALP = OUT / "obscure_validation.json"
CACHEP = OUT / "pypi_cache.json"


def pypi_exists(name, cache):
    k = norm(name)
    if k in cache:
        return cache[k]
    try:
        urllib.request.urlopen(f"https://pypi.org/pypi/{k}/json", timeout=15)
        cache[k] = True
    except urllib.error.HTTPError as e:
        cache[k] = (e.code != 404)
    except Exception:
        cache[k] = None
    time.sleep(0.12)
    return cache[k]


def main():
    if not RAW.exists():
        raise SystemExit(f"Khong thay {RAW}")
    rows = [json.loads(l) for l in RAW.open(encoding="utf-8") if l.strip()]
    print("=" * 66)
    print(f"BAI 07 - trich xuat lai tu {len(rows)} cau tra loi da co")
    print("=" * 66)

    models = {}
    for r in rows:
        models[r.get("model") or r.get("provider") or "?"] = \
            models.get(r.get("model") or r.get("provider") or "?", 0) + 1
    print("\nModel da tra loi:")
    for m, n in sorted(models.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {m}")
    if len(models) > 1:
        print("\n  *** CANH BAO: nhieu hon MOT model trong cung mot tap du lieu.")
        print("  *** Ty le ao giac do duoc la TRUNG BINH TRON cua cac model,")
        print("  *** khong phai tinh chat cua mot model nao. Bai bao khong")
        print("  *** duoc trinh bay con so nay nhu mot phep do tren mot model.")

    per_row = [extract(r["raw"]) for r in rows]
    names = [n for row in per_row for n in row]
    uniq = sorted(set(names))
    print(f"\n{len(names)} ten trich duoc, {len(uniq)} phan biet")

    cache = json.loads(CACHEP.read_text(encoding="utf-8")) if CACHEP.exists() else {}
    cache = {k: v for k, v in cache.items() if isinstance(v, bool)}
    print("Dang hoi PyPI ...")
    for n in uniq:
        pypi_exists(n, cache)
    CACHEP.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    hall = [n for n in uniq if cache.get(norm(n)) is False]
    occ = sum(1 for n in names if cache.get(norm(n)) is False)
    print(f"\n  ten co that : {len(uniq) - len(hall)}")
    print(f"  ten KHONG co: {len(hall)}  {hall}")
    print(f"\n  theo TEN phan biet: {len(hall)}/{len(uniq)} = {100*len(hall)/len(uniq):.2f}%")
    print(f"  theo LUOT        : {occ}/{len(names)} = {100*occ/len(names):.2f}%")

    VALP.write_text(json.dumps({
        "config": {"n_prompts": len(rows), "models": models,
                   "single_model": len(models) == 1,
                   "extractor": "v2 -- dung o token khong hop le hoac dau cau"},
        "n_names": len(names), "n_names_unique": len(uniq),
        "n_hallucinated_unique": len(hall), "n_hallucinated_occ": occ,
        "rate_unique_pct": round(100*len(hall)/len(uniq), 3),
        "rate_occ_pct": round(100*occ/len(names), 3),
        "hallucinated": hall, "names": uniq, "cache": cache,
    }, indent=1), encoding="utf-8")
    print(f"\nDa ghi -> {VALP}")


if __name__ == "__main__":
    main()
