import hashlib

# Lazy load sentence-transformers model
model = None

def get_embedding(text: str):
    """
    Generates a 384-dimensional embedding vector for the given text.
    Uses sentence-transformers/all-MiniLM-L6-v2 if installed, otherwise
    falls back to a hash-based deterministic mock vector.
    """
    global model
    if not text:
        return [0.0] * 384
        
    try:
        if model is None:
            print("EmbeddingHelper: Initializing sentence-transformers model...")
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Generate real embedding
        vector = model.encode(text)
        return vector.tolist()
    except Exception as e:
        # If sentence-transformers is not installed, fallback to a hash-based deterministic 384D vector.
        # This makes the app run out-of-the-box and computes stable cosine similarity.
        print(f"EmbeddingHelper: Using mock fallback embedding generator due to: {e}")
        
        # Calculate SHA256 of text to initialize seed
        sha = hashlib.sha256(text.encode("utf-8")).digest()
        
        # Generate 384 values from text hash
        values = []
        for i in range(384):
            # Deterministic calculation using character values and index
            val_byte = sha[i % len(sha)]
            val = (val_byte + i * 17) % 256
            # Map [0, 255] to [-1.0, 1.0]
            values.append(float(val) / 128.0 - 1.0)
            
        # Normalize the vector to unit length for cosine similarity
        norm = sum(x*x for x in values)**0.5
        if norm > 0:
            values = [x / norm for x in values]
            
        return values

