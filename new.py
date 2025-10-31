from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
from pinecone import (
    Pinecone,
    ServerlessSpec,
)
import numpy as np
import time

# 1. Load the PDF
pdf_path = r"C:/Users/shriv/OneDrive/Desktop/Current_Essentials_of_Medicine(1)(1)[1].pdf"
reader = PdfReader(pdf_path)

# 2. Extract text page-wise
pages_text = [page.extract_text() or "" for page in reader.pages]

# 3. Chunk the text (tune chunk size and overlap as needed)
def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

all_chunks = []
for page_text in pages_text:
    page_chunks = chunk_text(page_text)
    all_chunks.extend(page_chunks)

# 4. Load embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# 5. Convert chunks to vector embeddings
embeddings = model.encode(all_chunks, convert_to_tensor=False)

# 6. Initialize Pinecone
pc = Pinecone(api_key="pcsk_v7sfN_QKgiUyd5ehofrU1dFRPT1YrBNH7nPjgjxmTEjFxuYk89VUdMh9VSgLBzPDG7xsG")
index_name = "med-book"

# 7. Create index if it doesn't exist
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-west-2"),
        type="Dense"
    )
    while not pc.describe_index(index_name).status["ready"]:
        time.sleep(1)

# 8. Connect to index
index = pc.Index(index_name)

# 🔧 Combine text and vectors into a list of tuples
vector_data = list(zip(all_chunks, embeddings))

# 9. Batch upserts
batch_size = 100
for i in range(0, len(vector_data), batch_size):
    batch = vector_data[i:i+batch_size]
    vectors = [
        {
            "id": f"chunk-{i+j}",
            "values": vec.tolist(),
            "metadata": {"text": text}
        }
        for j, (text, vec) in enumerate(batch)
    ]
    index.upsert(vectors=vectors)

print(f"✅ Uploaded {len(vector_data)} vectors to Pinecone index '{index_name}'")