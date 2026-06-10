import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

ROOT = Path('.')
db_path = os.environ.get('CHROMA_DB_PATH', str(ROOT / 'chroma_db'))
col_name = os.environ.get('CHROMA_COLLECTION', 'day10_kb')
emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path=db_path)
col = client.get_collection(name=col_name, embedding_function=emb)

total = col.count()
print('Total chunks in Chroma:', total)

# Show all SLA chunks
all_data = col.get(where={"doc_id": "sla_p1_2026"})
print('\nAll sla_p1_2026 chunks in Chroma:')
for cid, doc, meta in zip(all_data['ids'], all_data['documents'], all_data['metadatas']):
    print('  id=' + cid[:30] + ' eff=' + meta.get('effective_date', '') + ' | ' + doc[:100])

# Query for gq_d10_06
question = "Neu khong co phan hoi voi ticket P1 sau bao lau thi he thong auto escalate?"
res = col.query(query_texts=[question], n_results=5)
docs = (res.get('documents') or [[]])[0]
metas = (res.get('metadatas') or [[]])[0]
print('\nTop-5 for gq_d10_06 (ASCII query):')
for i, (d, m) in enumerate(zip(docs, metas)):
    print('  #' + str(i+1) + ' doc=' + m.get('doc_id', '') + ' | ' + d[:120])

# Try with Vietnamese
question_vi = "Nếu không có phản hồi với ticket P1 sau bao lâu thì hệ thống auto escalate?"
res2 = col.query(query_texts=[question_vi], n_results=5)
docs2 = (res2.get('documents') or [[]])[0]
metas2 = (res2.get('metadatas') or [[]])[0]
print('\nTop-5 for gq_d10_06 (Vietnamese query):')
for i, (d, m) in enumerate(zip(docs2, metas2)):
    has10 = '10 phut' in d.lower().replace('\u00fa', 'u').replace('\u1ee3', 'o') or '10 ph' in d
    marker = ' <-- HAS 10ph' if has10 else ''
    print('  #' + str(i+1) + ' doc=' + m.get('doc_id', '') + ' | ' + d[:120] + marker)

blob = ' '.join(docs2).lower()
print('\nblob contains "10 phut":', '10 ph\u00fat' in blob)
print('blob contains "10 ph":', '10 ph' in blob)
