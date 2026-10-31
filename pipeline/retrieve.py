"""Similar past jobs: sentence-transformers (all-MiniLM-L6-v2, free, local) + FAISS flat inner-product, top-3.
One index per product family so a turned-part RFQ never matches a plate job.
"""
import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class Retriever:
    def __init__(self):
        self.jobs = json.loads((ROOT / "data" / "past_jobs.json").read_text())
        self.model = SentenceTransformer(MODEL_NAME)
        self.index = {}
        for fam in ("service_center", "machine_shop"):
            sub = [j for j in self.jobs if j["family"] == fam]
            vecs = self.model.encode([j["summary"] for j in sub], normalize_embeddings=True).astype("float32")
            ix = faiss.IndexFlatIP(vecs.shape[1])
            ix.add(vecs)
            self.index[fam] = (ix, sub)

    def top3(self, family, query):
        ix, sub = self.index[family]
        q = self.model.encode([query], normalize_embeddings=True).astype("float32")
        scores, idx = ix.search(q, 3)
        return [{"job_id": sub[i]["job_id"], "score": round(float(s), 4), "summary": sub[i]["summary"],
                 "total_price": sub[i]["total_price"], "lead_days": sub[i]["lead_days"]}
                for s, i in zip(scores[0], idx[0])]
