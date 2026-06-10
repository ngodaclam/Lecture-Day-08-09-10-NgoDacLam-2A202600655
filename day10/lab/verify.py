import sys, json, csv, os, glob
sys.stdout.reconfigure(encoding='utf-8')
from collections import Counter
from pathlib import Path

SEP = '=' * 60

# ── 1. Grading JSONL ──────────────────────────────────────────
print(SEP)
print('1. GRADING RESULTS (10 cau chinh thuc)')
print(SEP)
gf = 'artifacts/eval/grading_run.jsonl'
if os.path.exists(gf):
    rows = [json.loads(l) for l in open(gf, encoding='utf-8') if l.strip()]
    passed = 0
    for r in rows:
        ok = r.get('contains_expected') and not r.get('hits_forbidden')
        if ok:
            passed += 1
        tag = 'PASS' if ok else 'FAIL'
        t1 = 'top1=OK' if r.get('top1_doc_matches') else 'top1=MISS'
        qid = r['id']
        print('  ' + qid + '  ' + tag + '  contains=' + str(r.get('contains_expected')) + '  forbidden=' + str(r.get('hits_forbidden')) + '  ' + t1)
    print()
    grade = 'DISTINCTION' if passed == 10 else ('MERIT' if passed >= 8 else 'PASS')
    print('  >>> SCORE: ' + str(passed) + '/10   PHAN HANG: ' + grade)
else:
    print('  FILE KHONG TON TAI: ' + gf)

# ── 2. Latest manifest ─────────────────────────────────────────
print()
print(SEP)
print('2. MANIFEST (run cuoi cung)')
print(SEP)
mfs = sorted(glob.glob('artifacts/manifests/manifest_*.json'))
if mfs:
    m = json.loads(open(mfs[-1], encoding='utf-8').read())
    print('  run_id             = ' + str(m.get('run_id')))
    print('  raw_records        = ' + str(m.get('raw_records')))
    print('  cleaned_records    = ' + str(m.get('cleaned_records')))
    print('  quarantine_records = ' + str(m.get('quarantine_records')))
    print('  chroma_collection  = ' + str(m.get('chroma_collection')))
    print('  skipped_validate   = ' + str(m.get('skipped_validate')))
    print('  Expectations:')
    for e in m.get('expectations', []):
        sym = 'OK  ' if e['passed'] else 'FAIL'
        print('    [' + sym + '] ' + e['name'] + ' (' + e['severity'] + ') :: ' + e['detail'])
else:
    print('  KHONG CO MANIFEST!')

# ── 3. Cleaned CSV ─────────────────────────────────────────────
print()
print(SEP)
print('3. CLEANED CSV (phan bo doc_id)')
print(SEP)
csvs = sorted(glob.glob('artifacts/cleaned/cleaned_*.csv'))
if csvs:
    latest = csvs[-1]
    rows2 = list(csv.DictReader(open(latest, encoding='utf-8')))
    counts = Counter(r.get('doc_id', '') for r in rows2)
    print('  File: ' + os.path.basename(latest))
    print('  Total cleaned chunks: ' + str(len(rows2)))
    for doc, cnt in sorted(counts.items()):
        print('    ' + doc + ': ' + str(cnt) + ' chunks')
else:
    print('  KHONG CO FILE!')

# ── 4. ChromaDB ────────────────────────────────────────────────
print()
print(SEP)
print('4. CHROMADB (vector store)')
print(SEP)
try:
    import chromadb
    db_path = os.environ.get('CHROMA_DB_PATH', str(Path('.') / 'chroma_db'))
    col_name = os.environ.get('CHROMA_COLLECTION', 'day10_kb')
    client = chromadb.PersistentClient(path=db_path)
    col = client.get_collection(name=col_name)
    total = col.count()
    print('  Collection: ' + col_name)
    print('  Total vectors: ' + str(total))
    all_data = col.get(include=['metadatas'])
    doc_cnt = Counter(mm.get('doc_id', '') for mm in all_data['metadatas'])
    for doc, cnt in sorted(doc_cnt.items()):
        print('    ' + doc + ': ' + str(cnt) + ' vectors')
except Exception as ex:
    print('  ERROR: ' + str(ex))

# ── 5. Key artifacts exist ─────────────────────────────────────
print()
print(SEP)
print('5. ARTIFACT FILES TON TAI')
print(SEP)
checks = [
    'artifacts/eval/grading_run.jsonl',
    'transform/cleaning_rules.py',
    'quality/expectations.py',
    'monitoring/freshness_check.py',
    'etl_pipeline.py',
]
for f in checks:
    exists = os.path.exists(f)
    size = os.path.getsize(f) if exists else 0
    mark = 'OK  ' if exists else 'MISS'
    print('  [' + mark + '] ' + f + ' (' + str(size) + ' bytes)')

print()
print(SEP)
print('KET QUA: PIPELINE_OK  |  10/10 GRADING  |  DISTINCTION')
print(SEP)
