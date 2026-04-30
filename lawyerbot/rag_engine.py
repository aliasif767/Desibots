import os
import re
import fitz  # PyMuPDF
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

class PakistanLawEngine:
    def __init__(self):
        self.model = SentenceTransformer('BAAI/bge-small-en-v1.5')
        self.all_chunks = []
        self.index = None
        self.bm25 = None

    def ingest_pdfs(self, pdf_folder):
        """Cleans and chunks all PDFs in a folder."""
        raw_documents = []
        for file in os.listdir(pdf_folder):
            if file.endswith(".pdf"):
                path = os.path.join(pdf_folder, file)
                doc = fitz.open(path)
                text = ""
                for page in doc:
                    text += page.get_text("text") + "\n"
                
                # Basic Cleaning
                text = re.sub(r'\s+', ' ', text) # Remove extra whitespace
                
                # Smart Legal Chunking (Split by 'Section')
                pattern = r"(?=(?:Section|Article)\s+\d+[A-Z]?\s*:?)"
                sections = re.split(pattern, text)
                
                for sec in sections:
                    if len(sec.strip()) > 50:
                        self.all_chunks.append({
                            "text": sec.strip(),
                            "metadata": {"source": file}
                        })
        
        self._build_indices()

    def _build_indices(self):
        """Builds both FAISS and BM25 for hybrid search."""
        texts = [c['text'] for c in self.all_chunks]
        
        # Dense Index (FAISS)
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(np.array(embeddings))
        
        # Sparse Index (BM25)
        tokenized_corpus = [t.lower().split() for t in texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query, top_k=3):
        """Hybrid search combining Semantic and Keyword match."""
        # Dense search
        query_emb = self.model.encode([query], normalize_embeddings=True)
        _, dense_indices = self.index.search(np.array(query_emb), top_k)
        
        # Sparse search
        tokenized_query = query.lower().split()
        sparse_indices = np.argsort(self.bm25.get_scores(tokenized_query))[::-1][:top_k]
        
        # Combine unique results
        combined_indices = list(set(dense_indices[0].tolist() + sparse_indices.tolist()))
        return [self.all_chunks[i] for i in combined_indices[:top_k]]