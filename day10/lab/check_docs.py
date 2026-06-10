import csv, sys
sys.stdout.reconfigure(encoding='utf-8')

rows = list(csv.DictReader(open('data/raw/policy_export_dirty.csv', encoding='utf-8')))

suspects = ['access_control_sop', 'data_privacy_guideline', 'security_policy', 'legacy_catalog_xyz_zzz']
for doc in suspects:
    chunk = [r for r in rows if r.get('doc_id') == doc]
    print(f'--- {doc} ({len(chunk)} rows) ---')
    for r in chunk[:2]:
        eff = r.get('effective_date', '')
        text = (r.get('chunk_text') or '')[:120]
        print(f'  eff: {eff}')
        print(f'  text: {text}')
    print()

# Check grading questions for expected doc_ids
import json
with open('data/grading_questions.json', encoding='utf-8') as f:
    questions = json.load(f)

print("=== grading_questions.json - expect_top1_doc_id values ===")
doc_id_needed = set()
for q in questions:
    d = q.get('expect_top1_doc_id', '')
    if d:
        doc_id_needed.add(d)
        print(f"  Q: {q.get('question','')[:80]}")
        print(f"     expect_top1_doc_id: {d}")
        print()

print("=== doc_ids needed by grading but NOT in ALLOWED_DOC_IDS ===")
allowed = {'policy_refund_v4', 'sla_p1_2026', 'it_helpdesk_faq', 'hr_leave_policy'}
missing_from_allowed = doc_id_needed - allowed
for d in sorted(missing_from_allowed):
    print(f"  MISSING: {d}")
