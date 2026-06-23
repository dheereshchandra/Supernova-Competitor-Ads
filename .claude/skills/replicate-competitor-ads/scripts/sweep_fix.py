#!/usr/bin/env python3.13
"""Final safety net over generated.json: apply a few SAFE, idempotent romanization
fixes, and FLAG anything that needs a human / a targeted re-revise.

SAFE auto-fixes (Malayalam multiplier spelling/typo only):
  "classes-ne kaal " -> "classes-nekkaal "   |  "ezhu retti" -> "ezhu iratti"  |  "iratt{2,}i" -> "iratti"

FLAGS (reported, NOT auto-fixed — re-run the verify/revise step or fix by hand):
  bracketed [placeholder] in a romanized field; NON-LATIN script leaking into romanized;
  banned tokens: "15 days"/"one week"/"21 days"/"a month"/"free"/"₹"/rupee figures;
  "out loud"/"loudly"; "mother tongue"/"your own language".
(Brand-leak / spoken-"Miss Nova" are caught by the in-workflow verify agent.)

Usage: python3.13 sweep_fix.py --gen generated.json
Exit code is 0 always; read the printed FLAGS and decide.
"""
import argparse, json, re, pathlib

SAFE = [("classes-ne kaal ", "classes-nekkaal "), ("ezhu retti", "ezhu iratti")]
TRIPLE = re.compile(r"iratt+i")
BRACKET = re.compile(r"\[[^\]]+\]")
INDIC = re.compile(r"[ऀ-ॿ஀-௿ఀ-౿ಀ-೿ഀ-ൿ]")
BANNED = re.compile(r"\b(15 days|one week|in a week|21 days|in a month|free)\b|₹|\b\d+\s*rupee|\brupee\b", re.I)
LOUD = re.compile(r"out loud|loudly", re.I)
MT = re.compile(r"mother tongue|your own language", re.I)

def fixstr(s):
    if not s: return s, 0
    new = s
    for a, b in SAFE: new = new.replace(a, b)
    new = TRIPLE.sub("iratti", new)
    return new, (1 if new != s else 0)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--gen", required=True)
    args = ap.parse_args(); p = pathlib.Path(args.gen)
    res = json.load(open(p)); nfix = 0; flags = []
    for r in res:
        sc = r["script"]
        if sc.get("reviewer_note"):
            sc["reviewer_note"], d = fixstr(sc["reviewer_note"]); nfix += d
        for scn in sc.get("scenes", []):
            for f in ("english", "romanized"):
                scn[f], d = fixstr(scn.get(f, "")); nfix += d
        # flags (romanized only)
        for scn in sc.get("scenes", []):
            rom = scn.get("romanized", "") or ""
            if BRACKET.search(rom): flags.append((r["n"], f"bracket placeholder S{scn.get('n')}", BRACKET.search(rom).group(0)))
            if INDIC.search(rom): flags.append((r["n"], f"non-Latin leak S{scn.get('n')}", repr(INDIC.search(rom).group(0))))
        blob = " ".join((scn.get("english", "") or "") + " " + (scn.get("romanized", "") or "") for scn in sc.get("scenes", []))
        for rx, lbl in ((BANNED, "banned time/cost token"), (LOUD, "out-loud"), (MT, "mother-tongue")):
            m = rx.search(blob)
            if m: flags.append((r["n"], lbl, m.group(0)))
    json.dump(res, open(p, "w"), ensure_ascii=False, indent=2)
    print(f"[sweep_fix] applied {nfix} safe romanization fixes -> {p}")
    if flags:
        print(f"[sweep_fix] {len(flags)} FLAG(S) — fix by re-running verify/revise or by hand:")
        for n, lbl, val in flags:
            print(f"   #{n}: {lbl}: {val}")
    else:
        print("[sweep_fix] no residual flags — clean.")

if __name__ == "__main__":
    main()
