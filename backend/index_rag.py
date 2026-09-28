from rag_service import rebuild_index

if __name__ == "__main__":
    ok = rebuild_index()
    print("Chroma index ready" if ok else "Embedding index unavailable. Lexical retrieval fallback remains active.")
    raise SystemExit(0 if ok else 1)

