import pathlib,sys,threading
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0,'scripts')
from upload_to_r2 import read_csv, write_csv, local_file_for_row, load_env, MASTER_EXTRA_COLS
import boto3
IN=pathlib.Path('inputs/fb-ads-praktika-ai-2026-06-04.csv'); VID=pathlib.Path('videos/praktika-ai-2026-06-04'); MASTER=pathlib.Path('master/praktika-ai.csv')
env=load_env(pathlib.Path('.env')); today=date.today().isoformat()
ic,ir=read_csv(IN); mc,mr=read_csv(MASTER)
for c in ic:
    if c not in mc: mc.append(c)
for c in MASTER_EXTRA_COLS:
    if c not in mc: mc.append(c)
def key(r): return (str(r.get('ad_library_id','')).strip(), str(r.get('creative_index_in_ad','0')).strip() or '0')
mb={key(r):r for r in mr}
jobs=[]
for row in ir:
    k=key(row); em=mb.get(k)
    if em and em.get('r2_public_url'): continue
    lp,kind=local_file_for_row(row,VID,None)
    if kind in ('no-creative','video-missing','image-pending'): continue
    jobs.append((row,lp,kind,k))
print('pending uploads:',len(jobs),flush=True)
if not jobs:
    sys.exit(0)
jobs=jobs[:int(sys.argv[1]) if len(sys.argv)>1 else 400]
s3=boto3.client('s3',endpoint_url=env['R2_S3_ENDPOINT'],aws_access_key_id=env['R2_ACCESS_KEY_ID'],aws_secret_access_key=env['R2_SECRET_ACCESS_KEY'],region_name='auto')
base=env['R2_PUBLIC_URL_BASE']; bucket=env['R2_BUCKET']; lock=threading.Lock(); n=[0]
def up(j):
    row,lp,kind,k=j
    with open(lp,'rb') as fh: s3.put_object(Bucket=bucket,Key=lp.name,Body=fh,ContentType='image/jpeg' if kind=='image' else 'video/mp4')
    return j,f"{base}/{lp.name}"
with ThreadPoolExecutor(max_workers=12) as ex:
    for fut in as_completed([ex.submit(up,j) for j in jobs]):
        try: (row,lp,kind,k),url=fut.result()
        except Exception: continue
        with lock:
            nr={**row,'r2_public_url':url,'first_scrape_run_date':today,'latest_scrape_run_date':today}; mr.append(nr); mb[k]=nr; n[0]+=1
            if n[0]%10==0: write_csv(MASTER,mc,mr); print('ckpt',n[0],flush=True)
    write_csv(MASTER,mc,mr)
print('uploaded this run:',n[0],flush=True)
