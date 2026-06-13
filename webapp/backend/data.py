"""In-memory ad catalog: enriched CSVs ⋈ master CSVs, mtime-invalidated.

Mirrors the join in tools/csv-sync/sync_to_sheets.py: the enriched row is the
spine (ad_id), joined to the master row by the pipeline's id column, canonical
creative = the row with the lowest creative/variant index. Master schemas vary
per competitor (Creative Studio appends columns on first touch), so every
master read is column-tolerant.

Torn-read safety: the 11:30 git pull rewrites CSVs non-atomically; a reload
that throws keeps serving the previous snapshot.
"""
from __future__ import annotations

import csv
import json
import pathlib
import threading
import time

from .config import ANALYSIS_DIR, REPO

csv.field_size_limit(10 ** 9)

PIPELINES = ("facebook", "google")
ID_COL = {"facebook": "ad_library_id", "google": "creative_id"}
VAR_COL = {"facebook": "creative_index_in_ad", "google": "variant_index"}

VERDICTS = ("strong_winner", "winner", "undecided", "new", "loser")
SORTS = {
    "run_days": (lambda a: a["run_days"] or 0, True),
    "best_page_rank": (lambda a: a["best_page_rank"] if a["best_page_rank"] is not None else 10 ** 9, False),
    # rank normalized by page size: #3 on a 600-ad page beats #1 on a 30-ad page
    "rank_pct": (lambda a: (a["best_page_rank"] / a["page_count"])
                 if a["best_page_rank"] is not None and a["page_count"] else 10 ** 9, False),
    "first_seen": (lambda a: a["first_seen"] or "", True),
    "last_seen": (lambda a: a["last_seen"] or "", True),
    "ad_start_date": (lambda a: a["ad_start_date"] or "", True),
}

_STAT_THROTTLE_S = 15


def _int(v, default=None):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default


def _float(v, default=None):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return default


def _bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _json_list(v) -> list:
    try:
        out = json.loads(v) if v else []
        return out if isinstance(out, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _os_from_url(url: str) -> str:
    """Infer the target OS from an ad's destination link. Meta's Ad Library does
    NOT publish OS targeting, so a direct app-store link is the only unambiguous
    signal; web funnels / lead forms are OS-agnostic → "" (unknown)."""
    u = (url or "").lower()
    if "play.google.com" in u or "/store/apps/details" in u:
        return "Android"
    if "apps.apple.com" in u or "itunes.apple.com" in u:
        return "iOS"
    return ""


class Catalog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ads: dict[str, list[dict]] = {p: [] for p in PIPELINES}
        self._by_key: dict[tuple, dict] = {}
        self._groups: dict[tuple, list[dict]] = {}
        self._mtimes: dict[pathlib.Path, float] = {}
        self._last_stat = 0.0
        self._loaded_at: str | None = None
        self._timeline_cache: dict[tuple, tuple[float, dict]] = {}
        # Public R2 host (pub-*.r2.dev). Some pipeline scripts wrote asset URLs with
        # R2_PUBLIC_URL_BASE pointing at the *S3 endpoint* (…r2.cloudflarestorage.com),
        # which 400s in a browser; we rewrite those to the public host below.
        import os
        self._public_base = (os.environ.get("R2_PUBLIC_HOST")
                             or "https://pub-893b4a6a607b4221a894bf861da7914e.r2.dev").rstrip("/")

    def _publicize(self, url: str) -> str:
        if url and "r2.cloudflarestorage.com" in url:
            path = url.split("/", 3)[3] if url.count("/") >= 3 else ""
            return f"{self._public_base}/{path}"
        return url

    def _publicize_list(self, urls: list) -> list:
        return [self._publicize(u) for u in urls]

    # ---------- file inventory ----------

    def _files_for(self, pipeline: str) -> list[tuple[str, pathlib.Path, pathlib.Path]]:
        """[(slug, enriched_path, master_path)] for every competitor with both files."""
        out = []
        derived = ANALYSIS_DIR / "derived" / pipeline
        for p in sorted(derived.glob("*_enriched.csv")):
            slug = p.name[: -len("_enriched.csv")]
            master = REPO / pipeline / "master" / f"{slug}.csv"
            if master.is_file():
                out.append((slug, p, master))
        return out

    def _stale(self) -> bool:
        now = time.time()
        if now - self._last_stat < _STAT_THROTTLE_S and self._mtimes:
            return False
        self._last_stat = now
        current: dict[pathlib.Path, float] = {}
        for pipeline in PIPELINES:
            for _, enriched, master in self._files_for(pipeline):
                for f in (enriched, master):
                    try:
                        current[f] = f.stat().st_mtime
                    except OSError:
                        pass
        if current != self._mtimes:
            self._mtimes = current
            return True
        return False

    # ---------- loading ----------

    def _gdocs_sidecars(self) -> dict[str, dict]:
        """ad_id -> {rewrite, analysis} from step4_workspace/scenes/*.gdocs.json
        (the authoritative record — master gdoc columns exist only where Stage 9
        already ran once for that competitor)."""
        out: dict[str, dict] = {}
        for p in (REPO / "facebook" / "step4_workspace" / "scenes").glob("*.gdocs.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                out[str(d.get("ad_library_id") or p.name.split(".")[0])] = {
                    "rewrite": (d.get("supernova_doc") or {}).get("link", ""),
                    "analysis": (d.get("competitor_doc") or {}).get("link", ""),
                    # per-language localized Doc links (Title-cased lang -> url)
                    "locales": {lang.title(): (loc or {}).get("link", "")
                                for lang, loc in (d.get("locales") or {}).items()},
                    # per-language voiceover (TTS) track URLs (Title-cased lang -> url)
                    "tts_audio": {lang.title(): (v or {}).get("track_url", "")
                                  for lang, v in (d.get("tts") or {}).items()},
                }
            except (json.JSONDecodeError, OSError):
                continue
        return out

    def _transcript_ids(self, pipeline: str, slug: str) -> set[str]:
        d = ANALYSIS_DIR / "enrichment" / pipeline / "transcripts" / slug
        if not d.is_dir():
            return set()
        return {p.stem for p in d.glob("*.json")}

    def _load_pipeline(self, pipeline: str, gdocs: dict[str, dict]) -> list[dict]:
        id_col, var_col = ID_COL[pipeline], VAR_COL[pipeline]
        ads: list[dict] = []
        for slug, enriched_path, master_path in self._files_for(pipeline):
            # canonical master row per ad id = lowest creative/variant index
            master: dict[str, dict] = {}
            with master_path.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    aid = (r.get(id_col) or "").strip()
                    if not aid:
                        continue
                    cur = master.get(aid)
                    if cur is None or _int(r.get(var_col), 0) < _int(cur.get(var_col), 0):
                        master[aid] = r
            transcripts = self._transcript_ids(pipeline, slug)
            with enriched_path.open(encoding="utf-8-sig", newline="") as f:
                for e in csv.DictReader(f):
                    aid = (e.get("ad_id") or "").strip()
                    if not aid:
                        continue
                    m = master.get(aid, {})
                    ads.append(self._merge(pipeline, slug, aid, e, m, transcripts, gdocs))
        return ads

    def _merge(self, pipeline: str, slug: str, aid: str, e: dict, m: dict,
               transcripts: set[str], gdocs: dict[str, dict]) -> dict:
        sidecar = gdocs.get(aid, {}) if pipeline == "facebook" else {}
        rewrite_gdoc = (m.get("supernova_rewrite_gdoc_url") or "").strip() or sidecar.get("rewrite", "")
        analysis_gdoc = (m.get("competitor_analysis_gdoc_url") or "").strip() or sidecar.get("analysis", "")
        rewrite_docx = self._publicize((m.get("supernova_rewrite_docx_r2_url") or "").strip())
        analysis_docx = self._publicize((m.get("competitor_analysis_docx_r2_url") or "").strip())
        frames = self._publicize_list(_json_list(m.get("orig_frame_urls")))
        media_url = (m.get("r2_public_url") or "").strip()
        if pipeline == "facebook":
            ad_link = (m.get("ad_library_url") or "").strip()
            text = (m.get("ad_primary_text") or "").strip()
        else:
            ad_link = (m.get("creative_url") or "").strip()
            text = (m.get("ad_headline") or m.get("ad_description") or "").strip()
            if not media_url:
                media_url = (m.get("youtube_video_url") or "").strip()
        return {
            "pipeline": pipeline,
            "competitor": slug,
            "ad_id": aid,
            "page_id": (e.get("page_id") or "").strip(),
            "page_name": (e.get("page_name") or "").strip(),
            "verdict": (e.get("verdict") or "").strip(),
            "verdict_confidence": (e.get("verdict_confidence") or "").strip(),
            "media_type": (e.get("media_type") or "").strip(),
            "language": (e.get("language") or "").strip(),
            "presenter_type": (e.get("presenter_type") or "").strip(),
            "device_format": (e.get("device_format") or "").strip(),
            "production_type": (e.get("production_type") or "").strip(),
            "script_group_id": (e.get("script_group_id") or "").strip(),
            "replication_type": (e.get("replication_type") or "").strip(),
            "variant_role": (e.get("variant_role") or "").strip(),
            "page_count": _int(e.get("page_count")),
            "first_seen": (e.get("first_seen") or "").strip(),
            "last_seen": (e.get("last_seen") or "").strip(),
            "ad_start_date": (e.get("ad_start_date") or "").strip(),
            "run_days": _int(e.get("run_days")),
            "run_days_is_lower_bound": _bool(e.get("run_days_is_lower_bound")),
            "best_page_rank": _int(e.get("best_page_rank")),
            "median_page_rank": _int(e.get("median_page_rank")),
            "current_page_rank": _int(e.get("current_page_rank")),
            "frac_top_25": _float(e.get("frac_top_25")),
            "times_seen": _int(e.get("times_seen")),
            "is_retired": _bool(e.get("is_retired")),
            "present_latest": _bool(e.get("present_latest")),
            "ad_text": text,
            "cta": (m.get("ad_cta_label") or m.get("ad_cta_text") or "").strip(),
            "destination_url": (m.get("ad_destination_url") or "").strip(),
            "platform_os": _os_from_url(m.get("ad_destination_url") or ""),
            "ad_library_url": ad_link,
            "media_url": media_url,
            "thumb_url": frames[0] if frames else "",
            "orig_frame_urls": frames,
            "gen_panel_urls": self._publicize_list(_json_list(m.get("gen_panel_urls"))),
            "char_sheet_urls": self._publicize_list(_json_list(m.get("char_sheet_urls"))),
            "rewrite_gdoc_url": rewrite_gdoc,
            "analysis_gdoc_url": analysis_gdoc,
            "locales": sidecar.get("locales", {}),  # {Lang: localized Doc url}
            "tts_audio": {lg: self._publicize(u)  # {Lang: public voiceover url} (browser-playable)
                          for lg, u in (sidecar.get("tts_audio") or {}).items()},
            "rewrite_docx_url": rewrite_docx,
            "analysis_docx_url": analysis_docx,
            "rewrite_html_url": self._publicize((m.get("supernova_rewrite_html_r2_url") or "").strip()),
            "has_docs": bool(rewrite_docx and analysis_docx),
            "has_gdocs": bool(rewrite_gdoc and analysis_gdoc),
            "has_transcript": aid in transcripts,
            "scene_count": None,
        }

    def reload_if_stale(self) -> None:
        with self._lock:
            if not self._stale():
                return
            try:
                gdocs = self._gdocs_sidecars()
                ads = {p: self._load_pipeline(p, gdocs) for p in PIPELINES}
            except Exception:  # keep last good snapshot on torn reads
                return
            groups: dict[tuple, list[dict]] = {}
            for p in PIPELINES:
                for a in ads[p]:
                    if a["script_group_id"]:
                        groups.setdefault(
                            (p, a["competitor"], a["script_group_id"]), []).append(a)
            for members in groups.values():
                members.sort(key=lambda a: (-(a["run_days"] or 0), a["ad_id"]))
            self._ads = ads
            self._by_key = {(a["pipeline"], a["competitor"], a["ad_id"]): a
                            for p in PIPELINES for a in ads[p]}
            self._groups = groups
            self._loaded_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # ---------- queries ----------

    @property
    def loaded_at(self) -> str | None:
        return self._loaded_at

    def competitors(self) -> list[dict]:
        self.reload_if_stale()
        out = []
        for pipeline in PIPELINES:
            by_slug: dict[str, dict] = {}
            for a in self._ads[pipeline]:
                s = by_slug.setdefault(a["competitor"], {
                    "pipeline": pipeline, "slug": a["competitor"],
                    "page_name": a["page_name"], "total": 0, "with_media": 0,
                    "by_verdict": {v: 0 for v in VERDICTS}, "generated": 0,
                })
                s["total"] += 1
                if a["media_url"]:
                    s["with_media"] += 1
                if a["verdict"] in s["by_verdict"]:
                    s["by_verdict"][a["verdict"]] += 1
                if a["has_docs"] or a["has_gdocs"]:
                    s["generated"] += 1
            out.extend(sorted(by_slug.values(), key=lambda s: -s["total"]))
        return out

    def get(self, pipeline: str, slug: str, ad_id: str) -> dict | None:
        self.reload_if_stale()
        return self._by_key.get((pipeline, slug, ad_id))

    def list_ads(self, pipeline: str = "facebook", competitor: str = "",
                 verdict: list[str] | None = None, media_type: list[str] | None = None,
                 language: list[str] | None = None, device_format: list[str] | None = None,
                 page_name: list[str] | None = None, platform_os: str = "",
                 retired: str = "any", generated: str = "any", has_media: bool = True,
                 has_transcript: str = "any", q: str = "",
                 min_run_days: int | None = None, first_seen_days: int | None = None,
                 sort: str = "run_days", order: str = "", page: int = 1,
                 page_size: int = 60) -> dict:
        self.reload_if_stale()
        base = self._ads.get(pipeline, [])
        needle = q.lower() if q else ""

        # Each filter as a named predicate. Facets are computed with that facet's OWN
        # predicate excluded, so a filter's options stay stable when you select one
        # (picking "Video" must NOT make "Image" disappear from the media_type facet).
        preds: dict[str, callable] = {}
        if competitor:
            preds["competitor"] = lambda a: a["competitor"] == competitor
        if verdict:
            preds["verdict"] = lambda a: a["verdict"] in verdict
        if media_type:
            preds["media_type"] = lambda a: a["media_type"] in media_type
        if language:
            preds["language"] = lambda a: a["language"] in language
        if device_format:
            preds["device_format"] = lambda a: a["device_format"] in device_format
        if page_name:
            preds["page"] = lambda a: a["page_name"] in page_name
        if platform_os:
            preds["platform_os"] = lambda a: a["platform_os"] == platform_os
        if retired in ("yes", "no"):
            preds["retired"] = (lambda a: a["is_retired"]) if retired == "yes" \
                else (lambda a: not a["is_retired"])
        if generated in ("yes", "no"):
            preds["generated"] = (lambda a: a["has_docs"] or a["has_gdocs"]) if generated == "yes" \
                else (lambda a: not (a["has_docs"] or a["has_gdocs"]))
        if has_media:
            preds["has_media"] = lambda a: bool(a["media_url"])
        if has_transcript == "yes":
            preds["has_transcript"] = lambda a: a["has_transcript"]
        if first_seen_days is not None:
            import datetime
            cutoff = (datetime.date.today()
                      - datetime.timedelta(days=first_seen_days)).isoformat()
            preds["first_seen"] = lambda a: (a["first_seen"] or "") >= cutoff
        if min_run_days is not None:
            preds["min_run_days"] = lambda a: (a["run_days"] or 0) >= min_run_days
        if needle:
            preds["q"] = lambda a: (needle in a["ad_text"].lower()
                                    or needle in a["page_name"].lower() or needle in a["ad_id"])

        def apply(items, skip: str = "") -> list[dict]:
            for name, pred in preds.items():
                if name == skip:
                    continue
                items = [a for a in items if pred(a)]
            return items

        ads = apply(base)

        # Facet counts: for each dimension, exclude its own selection so all options remain visible.
        # dim (= its predicate name) -> the ad field counted.
        facet_dims = {"verdict": "verdict", "media_type": "media_type",
                      "language": "language", "device_format": "device_format"}
        if competitor:  # page facet only within one competitor (names collide across them)
            facet_dims["page"] = "page_name"
        facets = {}
        for dim, field in facet_dims.items():
            facets[dim] = {}
            for a in apply(base, skip=dim):
                v = a[field]
                if v:
                    facets[dim][v] = facets[dim].get(v, 0) + 1

        # OS coverage for the disclaimer: counted over the current view but with the
        # OS filter itself excluded, so the % is stable whether or not iOS/Android is
        # selected. OS is only known for ads whose destination is a direct store link.
        os_view = apply(base, skip="platform_os")
        os_coverage = {
            "ios": sum(1 for a in os_view if a["platform_os"] == "iOS"),
            "android": sum(1 for a in os_view if a["platform_os"] == "Android"),
            "total": len(os_view),
        }
        os_coverage["known"] = os_coverage["ios"] + os_coverage["android"]

        key, default_desc = SORTS.get(sort, SORTS["run_days"])
        desc = default_desc if order == "" else (order == "desc")
        ads = sorted(ads, key=key, reverse=desc)

        total = len(ads)
        page = max(1, page)
        start = (page - 1) * page_size
        return {"total": total, "page": page, "page_size": page_size,
                "facets": facets, "os_coverage": os_coverage,
                "ads": ads[start:start + page_size]}

    # ---------- detail extras ----------

    def transcript(self, pipeline: str, slug: str, ad_id: str) -> dict | None:
        p = ANALYSIS_DIR / "enrichment" / pipeline / "transcripts" / slug / f"{ad_id}.json"
        if not p.is_file():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return {k: d.get(k) for k in
                    ("transcript", "summary", "on_screen_text", "duration_s", "language")}
        except (json.JSONDecodeError, OSError):
            return None

    def rank_timeline(self, pipeline: str, slug: str, ad_id: str) -> list[dict]:
        """[{date, rank}] for the sparkline, from {slug}_rank_timeline.csv
        (parsed once per competitor, cached by mtime)."""
        p = ANALYSIS_DIR / "derived" / pipeline / f"{slug}_rank_timeline.csv"
        if not p.is_file():
            return []
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return []
        cached = self._timeline_cache.get((pipeline, slug))
        if cached is None or cached[0] != mtime:
            by_ad: dict[str, list[dict]] = {}
            try:
                with p.open(encoding="utf-8-sig", newline="") as f:
                    for r in csv.DictReader(f):
                        aid = (r.get("ad_id") or "").strip()
                        rank = _int(r.get("page_rank"))
                        date = (r.get("scrape_date") or "").strip()
                        if aid and date and rank is not None:
                            by_ad.setdefault(aid, []).append({"date": date, "rank": rank})
            except OSError:
                return []
            for rows in by_ad.values():
                rows.sort(key=lambda r: r["date"])
            self._timeline_cache[(pipeline, slug)] = (mtime, by_ad)
            cached = self._timeline_cache[(pipeline, slug)]
        return cached[1].get(ad_id, [])

    # ---------- script groups ----------

    def group_members(self, pipeline: str, slug: str, gid: str) -> list[dict]:
        """All ads in a script group, longest-running first."""
        self.reload_if_stale()
        return list(self._groups.get((pipeline, slug, gid), []))

    def group_meta(self, pipeline: str, slug: str, gid: str) -> dict:
        """Unfiltered group rollup (the grid may be showing a narrowed subset)."""
        members = self._groups.get((pipeline, slug, gid), [])
        return {
            "size": len(members),
            "languages_total": len({a["language"] for a in members if a["language"]}),
            "winners_total": sum(1 for a in members
                                 if a["verdict"] in ("strong_winner", "winner")),
        }

    def related(self, ad: dict, limit: int = 24) -> list[dict]:
        """Other ads in the same script group (competitor ran N variants)."""
        gid = ad["script_group_id"]
        if not gid:
            return []
        members = self._groups.get((ad["pipeline"], ad["competitor"], gid), [])
        return [a for a in members if a["ad_id"] != ad["ad_id"]][:limit]


_catalog: Catalog | None = None


def catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
    return _catalog
