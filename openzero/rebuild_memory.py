import sys
import os
# Add brain folder to path so we can import rag_engine
sys.path.append(os.path.join(os.path.dirname(__file__), 'brain'))
try:
    from rag_engine import ZeroMemory
    print(">>> MEMORY PROTOCOL INITIATED.")
    z = ZeroMemory()
    # Force ingestion of text files in knowledge/
    z.ingest() 
    print(">>> KNOWLEDGE BASE ACTIVE.")
except Exception as e:
    print(f">>> MEMORY ERROR (NON-FATAL): {e}")
