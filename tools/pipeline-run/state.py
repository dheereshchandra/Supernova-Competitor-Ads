#!/usr/bin/env python3.13
"""state.py — machine-readable run-state + heartbeat for the durable pipeline runner.

The durable runner (run_batch.sh) calls this to record progress; status.sh and the
Claude monitoring loop read it. State lives at analysis/state/pipeline-run.json
(per-clone runtime state — gitignored). A "progress fingerprint" (total transcripts
+ master rows + today's downloaded videos across all competitors) is recomputed on
every heartbeat; if it stops changing while the runner is alive, that's a STALL.

Subcommands:
  ensure  <run_id> <slug...>     create/reset state for TODAY (resume if same day)
  pid     <pid>                   record the live runner PID
  current <slug> <stage>         set the in-progress competitor + stage label
  set     <slug> <status> [att]   set a competitor's status (done|failed|running|pending) + attempts
  heartbeat                       refresh heartbeat ts + recompute the progress fingerprint
  summary                         human-readable dashboard (for status.sh / the operator)
  verdict                         one word for the monitor loop: done|running|stalled|dead|empty
  pending                         space-separated slugs still needing work (not done/perm-failed)
"""
from __future__ import annotations
import json, os, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "analysis" / "state" / "pipeline-run.json"
STALL_MINUTES = 30          # runner alive but fingerprint unchanged this long ⇒ STALLED.
                            # Must exceed the longest no-progress window — the scrape
                            # stage is in-memory (nothing on disk grows) for up to
                            # ~15 min on a 6-page competitor, so 30 leaves margin.
MAX_ATTEMPTS = 3            # give up on a competitor after this many failed passes

def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

def _today() -> str:
    return datetime.date.today().isoformat()

def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}

def _save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(STATE)

def _fingerprint(slugs: list[str]) -> int:
    """Cheap monotonic progress signal: more transcripts/master-rows/videos = progress."""
    total = 0
    enr = ROOT / "analysis" / "enrichment" / "facebook" / "transcripts"
    mas = ROOT / "facebook" / "master"
    vids = ROOT / "facebook" / "videos"
    inp = ROOT / "facebook" / "inputs"
    for s in slugs:
        d = enr / s
        if d.is_dir():
            total += sum(1 for _ in d.glob("*.json"))
        m = mas / f"{s}.csv"
        if m.is_file():
            # row count ~ bytes/64 is enough as a monotonic signal without parsing
            total += sum(1 for _ in m.open("rb")) - 1
        for vd in vids.glob(f"{s}-*"):
            if vd.is_dir():
                total += sum(1 for _ in vd.glob("*.mp4"))
        # input snapshots: bumps when a scrape COMPLETES (resets the stall timer for
        # the next stages, so a long but healthy scrape isn't flagged STALLED).
        total += sum(1 for _ in inp.glob(f"fb-ads-{s}-*.csv"))
    return max(total, 0)

def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False

def _age_min(ts: str | None) -> float:
    if not ts:
        return 1e9
    try:
        t = datetime.datetime.fromisoformat(ts)
        now = datetime.datetime.now(t.tzinfo) if t.tzinfo else datetime.datetime.now()
        return (now - t).total_seconds() / 60.0
    except Exception:
        return 1e9

def cmd_ensure(run_id, slugs):
    d = _load()
    if d.get("date") != _today() or not d.get("competitors"):
        d = {"date": _today(), "run_id": run_id, "started_at": _now(),
             "pid": None, "competitors": slugs, "current": None, "current_stage": None,
             "heartbeat": _now(), "fingerprint": _fingerprint(slugs),
             "fingerprint_changed_at": _now(),
             "per_competitor": {s: {"status": "pending", "attempts": 0} for s in slugs}}
    else:
        # same-day resume: keep statuses, ensure every requested slug is present
        for s in slugs:
            d["per_competitor"].setdefault(s, {"status": "pending", "attempts": 0})
        d["competitors"] = slugs
        d["run_id"] = run_id
    _save(d)

def cmd_pid(pid):
    d = _load(); d["pid"] = int(pid); _save(d)

def cmd_current(slug, stage):
    d = _load(); d["current"] = slug; d["current_stage"] = stage; _save(d)

def cmd_set(slug, status, attempts=None):
    d = _load()
    pc = d.setdefault("per_competitor", {}).setdefault(slug, {"status": "pending", "attempts": 0})
    pc["status"] = status
    if attempts is not None:
        pc["attempts"] = int(attempts)
    if status == "done":
        pc["finished_at"] = _now()
    _save(d)

def cmd_heartbeat():
    d = _load()
    if not d:
        return
    fp = _fingerprint(d.get("competitors", []))
    if fp != d.get("fingerprint"):
        d["fingerprint"] = fp
        d["fingerprint_changed_at"] = _now()
    d["heartbeat"] = _now()
    _save(d)

def _all_settled(d) -> bool:
    pc = d.get("per_competitor", {})
    return all(v.get("status") == "done" or
               (v.get("status") == "failed" and v.get("attempts", 0) >= MAX_ATTEMPTS)
               for v in pc.values()) and bool(pc)

def cmd_pending():
    d = _load()
    out = [s for s in d.get("competitors", [])
           if not (d["per_competitor"].get(s, {}).get("status") == "done"
                   or (d["per_competitor"].get(s, {}).get("status") == "failed"
                       and d["per_competitor"].get(s, {}).get("attempts", 0) >= MAX_ATTEMPTS))]
    print(" ".join(out))

def cmd_verdict():
    d = _load()
    if not d or not d.get("per_competitor"):
        print("empty"); return
    if _all_settled(d):
        print("done"); return
    alive = _pid_alive(d.get("pid"))
    if not alive:
        print("dead"); return
    if _age_min(d.get("fingerprint_changed_at")) > STALL_MINUTES and _age_min(d.get("heartbeat")) < 3:
        print("stalled"); return
    print("running")

def cmd_summary():
    d = _load()
    if not d:
        print("no run state yet (analysis/state/pipeline-run.json absent)"); return
    pid = d.get("pid"); alive = _pid_alive(pid)
    print(f"Pipeline run {d.get('run_id','?')}  ({d.get('date','?')})")
    print(f"  runner pid {pid} {'ALIVE' if alive else 'NOT running'} | "
          f"heartbeat {_age_min(d.get('heartbeat')):.1f}m ago | "
          f"progress {_age_min(d.get('fingerprint_changed_at')):.1f}m since last change "
          f"(fp={d.get('fingerprint')})")
    cur = d.get("current")
    if cur:
        print(f"  current: {cur}  [stage {d.get('current_stage')}]")
    order = {"done": 0, "running": 1, "failed": 2, "pending": 3}
    for s in d.get("competitors", []):
        v = d["per_competitor"].get(s, {})
        st = v.get("status", "pending"); att = v.get("attempts", 0)
        mark = {"done": "✓", "running": "▶", "failed": "✗", "pending": "·"}.get(st, "?")
        extra = f" (attempt {att})" if att else ""
        fin = f" @ {v.get('finished_at','')[-8:]}" if v.get("finished_at") else ""
        print(f"   {mark} {s:<16} {st}{extra}{fin}")
    v = None
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_verdict()
    print(f"  OVERALL: {buf.getvalue().strip()}")

def main():
    a = sys.argv[1:]
    if not a:
        sys.exit("usage: state.py <ensure|pid|current|set|heartbeat|summary|verdict|pending> ...")
    c = a[0]
    if c == "ensure":   cmd_ensure(a[1], a[2:])
    elif c == "pid":    cmd_pid(a[1])
    elif c == "current":cmd_current(a[1], a[2] if len(a) > 2 else "")
    elif c == "set":    cmd_set(a[1], a[2], a[3] if len(a) > 3 else None)
    elif c == "heartbeat": cmd_heartbeat()
    elif c == "summary":   cmd_summary()
    elif c == "verdict":   cmd_verdict()
    elif c == "pending":   cmd_pending()
    else: sys.exit(f"unknown subcommand: {c}")

if __name__ == "__main__":
    main()
