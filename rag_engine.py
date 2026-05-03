"""
rag_engine.py
=============
Knowledge retrieval + Gemini-powered clinical explanation.
- ChromaDB + sentence-transformers retrieval
- LLM generation via google-genai (Gemini)
- Rule-based fallback if all Gemini models fail
"""
import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sentence_transformers import SentenceTransformer

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

KB_DIR = Path(__file__).parent / "knowledge_base"
DB_DIR = Path(__file__).parent / "chroma_db"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLL_NAME = "burn_kb"
TOP_K = 4
CHUNK_WORDS = 350

TEXT_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]


class RAGEngine:
    def __init__(self):
        print("[RAG] Initializing...")
        self._emb = SentenceTransformer(EMBED_MODEL)
        print("[RAG] Embedding model loaded.")

        self._client = chromadb.PersistentClient(path=str(DB_DIR))
        existing = [c.name for c in self._client.list_collections()]

        if COLL_NAME in existing:
            self._col = self._client.get_collection(COLL_NAME)
            print(f"[RAG] Collection loaded — {self._col.count()} chunks.")
        else:
            self._col = self._client.create_collection(COLL_NAME)
            self._build_index()

        print("[RAG] Ready.")

    def _build_index(self):
        files = list(KB_DIR.glob("*.txt"))
        if not files:
            print("[WARN] No knowledge_base files found.")
            return

        docs, ids, metas = [], [], []
        idx = 0
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                words = text.split()
                chunks = [" ".join(words[i:i + CHUNK_WORDS])
                          for i in range(0, len(words), CHUNK_WORDS)]
                for ch in chunks:
                    if len(ch.strip()) > 40:
                        docs.append(ch)
                        ids.append(f"c{idx}")
                        metas.append({"source": f.name})
                        idx += 1
            except Exception as e:
                print(f"[WARN] {f.name}: {e}")

        if docs:
            embs = self._emb.encode(docs).tolist()
            self._col.add(documents=docs, embeddings=embs, ids=ids, metadatas=metas)
            print(f"[RAG] Indexed {len(docs)} chunks from {len(files)} files.")

    def _embed(self, text: str) -> list:
        return self._emb.encode([text])[0].tolist()

    def _llm(self, system: str, user: str, model_name: str) -> str:
        """Gemini text generation with system + user prompt."""
        response = client.models.generate_content(
            model=model_name,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.3,
                max_output_tokens=600,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Empty content from Gemini")
        return text

    def _fallback(self, tbsa: float, age: int, chunks: list) -> str:
        """Rule-based fallback if all Gemini models fail."""
        if tbsa >= 40:
            cat, tips = "KRITIS", [
                "Aktivasi burn team segera",
                "Amankan airway — pertimbangkan intubasi dini",
                "Resusitasi cairan agresif sesuai Parkland",
                "Pasang 2 IV line besar (>18G) di area tidak terbakar",
                "Kateter urin — target urine 0.5–1 mL/kg/jam",
                "Transfer ke Burn Center tersier setelah stabilisasi",
            ]
        elif tbsa >= 20:
            cat, tips = "MAYOR", [
                "Rawat ICU / unit luka bakar",
                "Resusitasi cairan sesuai Parkland",
                "Monitor urine output tiap jam, target 0.5–1 mL/kg/jam",
                "Cek elektrolit & fungsi ginjal tiap 4–6 jam",
                "Wound care dan tutup luka",
            ]
        elif tbsa >= 10:
            cat, tips = "MODERAT", [
                "Rawat inap dipertimbangkan",
                "Cairan IV sesuai jadwal Parkland",
                "Monitor urine output dan tanda vital",
                "Evaluasi ulang setelah 24 jam",
            ]
        else:
            cat, tips = "MINOR", [
                "Rawat jalan jika tidak ada komplikasi",
                "Perawatan luka dengan balutan non-adherent",
                "Analgesik adekuat",
                "Kontrol ulang 48–72 jam",
            ]

        lines = [
            f"KLASIFIKASI: {cat} (TBSA {tbsa:.1f}%)\n",
            "PRIORITAS MANAJEMEN:",
        ] + [f"  • {t}" for t in tips] + [
            "",
            "MONITORING CAIRAN:",
            "  • Titrasi infus berdasarkan urine output aktual",
            "  • Urine output < target → tingkatkan rate 20%",
            "  • Urine output > 1 mL/kg/jam → kurangi rate 20%",
        ]

        if age < 10:
            lines += ["", "⚠️ PEDIATRIK: Pertimbangkan formula Galveston",
                      "   Monitor glukosa darah tiap 2–4 jam"]
        if age > 60:
            lines += ["", "⚠️ GERIATRIK: Monitor hemodinamik lebih ketat"]

        if chunks:
            snip = chunks[0][:250].strip()
            lines += ["", "INFORMASI DARI BASIS PENGETAHUAN:", f"  {snip}..."]

        lines += [
            "",
            "Referensi: Parkland Formula (Baxter CR, 1974) | Lund-Browder Chart",
            "           ABA Guidelines on Management of Acute Burns (2022)",
        ]
        return "\n".join(lines)

    def query(self, question: str, tbsa: float, age: int) -> dict:
        chunks, sources = [], []
        try:
            emb = self._embed(question)
            results = self._col.query(
                query_embeddings=[emb],
                n_results=min(TOP_K, self._col.count()),
                include=["documents", "metadatas"],
            )
            chunks = results["documents"][0]
            sources = list(dict.fromkeys(
                m.get("source", "") for m in results["metadatas"][0] if m.get("source")
            ))
        except Exception as e:
            print(f"[WARN] Retrieval: {e}")

        refs = (
            [s.replace(".txt", "").replace("_", " ").title() for s in sources]
            if sources else [
                "Parkland Formula (Baxter CR, 1974)",
                "Lund-Browder Chart",
                "ABA Guidelines on Management of Acute Burns (2022)",
            ]
        )

        context = "\n\n---\n\n".join(chunks) if chunks else \
            "Gunakan pengetahuan umum kedokteran luka bakar."

        sys_p = (
            "Kamu adalah dokter spesialis gawat darurat dengan keahlian luka bakar. "
            "Jawab pertanyaan klinis berdasarkan konteks medis yang diberikan. "
            "Jawab dalam Bahasa Indonesia, singkat, dan gunakan bullet points."
        )
        usr_p = (
            f"Konteks medis:\n{context}\n\n"
            f"Data pasien: Usia {age} tahun, TBSA {tbsa:.1f}%\n"
            f"Pertanyaan: {question}"
        )

        for model_name in TEXT_MODELS:
            try:
                exp = self._llm(sys_p, usr_p, model_name)
                print(f"[RAG] OK via {model_name}")
                return {"explanation": exp, "references": refs}
            except Exception as e:
                print(f"[WARN] LLM {model_name}: {e}")

        return {"explanation": self._fallback(tbsa, age, chunks), "references": refs}
