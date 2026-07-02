import os
import chromadb
from sentence_transformers import SentenceTransformer

class ZeroMemory:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=os.path.expanduser("~/openzero/chroma_db"))
        self.collection = self.client.get_or_create_collection(name="zero_knowledge")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        if self.collection.count() == 0: self.ingest_knowledge()

    def ingest_knowledge(self):
        kb_path = os.path.expanduser("~/openzero/knowledge")
        if not os.path.exists(kb_path): return
        for fn in os.listdir(kb_path):
            if fn.endswith(".txt"):
                with open(os.path.join(kb_path, fn), 'r') as f:
                    content = f.read()
                    self.collection.add(ids=[fn], documents=[content], 
                                     embeddings=self.model.encode([content]).tolist(), 
                                     metadatas=[{"source": fn}])

    def search(self, query):
        results = self.collection.query(query_embeddings=self.model.encode([query]).tolist(), n_results=2)
        return "\n".join(results['documents'][0]) if results['documents'] else ""
