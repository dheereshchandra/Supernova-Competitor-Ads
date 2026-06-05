#!/usr/bin/env python3
"""One-off parallel merge that mirrors upload_to_r2.py's exact decision logic
and master semantics, but uploads concurrently and checkpoints atomically.

Same unique key (ad_library_id, creative_index_in_ad), same r2_key (filename),
same carry-forward / image-pending / upsert rules. Safe to re-run (idempotent):
rows already carrying an r2_public_url take the carry-forward path.
"""
import pathlib, sys, threading
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "scripts")
from upload_to_r2 import (read_csv, write_csv, local_file_for_row,
                          load_env, MASTER_EXTRA_COLS)

import boto3

IN = pathlib.Path("inputs/fb-ads-praktika-ai-2026-06-04.csv")
VID = pathlib.Path("videos/praktika-ai-2026-06-04")
MASTER = pathlib.Path("master/praktika-ai.csv")
env = load_env(pathlib.Path(".env"))
today = date.today().isoformat()

input_cols, input_rows = read_csv(IN)
master_cols, master_rows = read_csv(MASTER)
for c in input_cols:
    if c not in master_cols:
        master_cols.append(c)
for c in MASTER_EXTRA_COLS:
    if c not in master_cols:
        master_cols.append(c)

def key(r):
    return (str(r.get("ad_library_id", "")).strip(),
            str(r.get("creative_index_in_ad", "0")).strip() or "0")

master_by = {key(r): r for r in master_rows}

counts = {"uploaded": 0, "carried-forward": 0, "image-pending": 0,
          "video-missing": 0, "no-creative": 0, "error": 0}

# Pass 1: classify. Apply non-upload mutations immediately; collect upload jobs.
upload_jobs = []  # (row, local_path, kind, k)
for row in input_rows:
    k = key(row)
    em = master_by.get(k)
    if em and em.get("r2_public_url"):
        for c in input_cols:
            if c == "first_scrape_run_date":
                continue
            em[c] = row.get(c, em.get(c, ""))
        em["latest_scrape_run_date"] = today
        counts["carried-forward"] += 1
        continue
    local_path, kind = local_file_for_row(row, VID, None)
    if kind == "no-creative":
        counts["no-creative"] += 1
        continue
    if kind == "image-pending":
        counts["image-pending"] += 1
        if em:
            em.update({c: row.get(c, em.get(c, "")) for c in input_cols})
            em["latest_scrape_run_date"] = today
        else:
            nr = {**row, "r2_public_url": "",
                  "first_scrape_run_date": today, "latest_scrape_run_date": today}
            master_rows.append(nr)
            master_by[k] = nr
        continue
    if kind == "video-missing":
        counts["video-missing"] += 1
        continue
    upload_jobs.append((row, local_path, kind, k))

print(f"[plan] carry-forward={counts['carried-forward']} image-pending={counts['image-pending']} "
      f"video-missing={counts['video-missing']} to-upload={len(upload_jobs)}")
sys.stdout.flush()

s3 = boto3.client("s3", endpoint_url=env["R2_S3_ENDPOINT"],
                  aws_access_key_id=env["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
                  region_name="auto")
base = env["R2_PUBLIC_URL_BASE"]
bucket = env["R2_BUCKET"]
lock = threading.Lock()
done = [0]

def do_upload(job):
    row, local_path, kind, k = job
    r2_key = local_path.name
    ct = "image/jpeg" if kind == "image" else "video/mp4"
    with open(local_path, "rb") as fh:
        s3.put_object(Bucket=bucket, Key=r2_key, Body=fh, ContentType=ct)
    return job, f"{base}/{r2_key}"

with ThreadPoolExecutor(max_workers=10) as ex:
    futs = {ex.submit(do_upload, j): j for j in upload_jobs}
    for fut in as_completed(futs):
        job = futs[fut]
        row, local_path, kind, k = job
        try:
            _, url = fut.result()
        except Exception as e:
            counts["error"] += 1
            print(f"[err] {row.get('ad_library_id')}: {type(e).__name__}: {e}")
            continue
        with lock:
            em = master_by.get(k)
            if em:
                em.update({c: row.get(c, em.get(c, "")) for c in input_cols})
                em["r2_public_url"] = url
                em["latest_scrape_run_date"] = today
                if not em.get("first_scrape_run_date"):
                    em["first_scrape_run_date"] = today
            else:
                nr = {**row, "r2_public_url": url,
                      "first_scrape_run_date": today, "latest_scrape_run_date": today}
                master_rows.append(nr)
                master_by[k] = nr
            counts["uploaded"] += 1
            done[0] += 1
            if done[0] % 100 == 0:
                write_csv(MASTER, master_cols, master_rows)
                print(f"[checkpoint] uploaded={done[0]}/{len(upload_jobs)} master_rows={len(master_rows)}")
                sys.stdout.flush()

write_csv(MASTER, master_cols, master_rows)
print(f"[final] {counts} master_rows={len(master_rows)}")
