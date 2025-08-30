import os
import requests
import json
from docx import Document
import pypdf
from bs4 import BeautifulSoup
import pickle
import faiss
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize OpenAI client with API key from config or environment
def _get_openai_client():
    """Get OpenAI client with proper API key"""
    try:
        from app.config.api_config import get_openai_api_key
        api_key = get_openai_api_key()
        if not api_key:
            # Fallback to environment variable
            api_key = os.getenv("OPENAI_API_KEY")
        return OpenAI(api_key=api_key)
    except ImportError:
        # Fallback if api_config is not available
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

client = _get_openai_client()

def extract_text_from_docx(file_path):
    """Extract text from DOCX file"""
    try:
        doc = Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text.strip())
        return "\n".join(text)
    except Exception as e:
        print(f"Error extracting text from DOCX: {e}")
        return ""

def extract_text_from_pdf(file_path):
    """Extract text from PDF file"""
    try:
        text = []
        with open(file_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text.strip():
                    text.append(page_text.strip())
        return "\n".join(text)
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

def fetch_content_from_url(url):
    """Fetch content from URL (HTML or JSON)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        
        if 'application/json' in content_type:
            # Handle JSON content
            json_data = response.json()
            return json.dumps(json_data, indent=2)
        elif 'text/html' in content_type:
            # Handle HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            # Get text content
            text = soup.get_text()
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text
        else:
            # Try to get text content anyway
            return response.text
    except Exception as e:
        print(f"Error fetching content from URL: {e}")
        return ""

def chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into overlapping chunks"""
    if not text:
        return []
    
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        if end > text_length:
            end = text_length
        
        chunk = text[start:end]
        chunks.append(chunk)
        
        if end == text_length:
            break
        
        start = end - overlap
    
    return chunks

def create_embeddings(chunks):
    """Create embeddings for text chunks"""
    embeddings = []
    for chunk in chunks:
        try:
            response = client.embeddings.create(
                input=chunk,
                model="text-embedding-3-small"
            )
            embedding = np.array(response.data[0].embedding, dtype="float32")
            embeddings.append(embedding)
        except Exception as e:
            print(f"Error creating embedding: {e}")
            # Create a zero embedding as fallback
            embeddings.append(np.zeros(1536, dtype="float32"))
    
    return np.array(embeddings)

def process_knowledge_base(kb_id, kb_type, source_path):
    """Process a knowledge base and create embeddings"""
    try:
        # Extract text based on type
        if kb_type == "file":
            if source_path.lower().endswith('.docx'):
                text = extract_text_from_docx(source_path)
            elif source_path.lower().endswith('.pdf'):
                text = extract_text_from_pdf(source_path)
            else:
                print(f"Unsupported file type: {source_path}")
                return False
        elif kb_type == "url":
            text = fetch_content_from_url(source_path)
        else:
            print(f"Unsupported knowledge base type: {kb_type}")
            return False
        
        if not text:
            print(f"No text extracted from {source_path}")
            return False
        
        # Chunk the text
        chunks = chunk_text(text)
        if not chunks:
            print(f"No chunks created from {source_path}")
            return False
        
        # Create embeddings
        embeddings = create_embeddings(chunks)
        
        # Create FAISS index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)
        
        # Save index and chunks
        kb_folder = f"app/knowledge_bases/{kb_id}"
        os.makedirs(kb_folder, exist_ok=True)
        
        index_path = f"{kb_folder}/index.faiss"
        chunks_path = f"{kb_folder}/chunks.pkl"
        
        faiss.write_index(index, index_path)
        with open(chunks_path, "wb") as f:
            pickle.dump(chunks, f)
        
        print(f"Successfully processed knowledge base {kb_id}")
        return True
        
    except Exception as e:
        print(f"Error processing knowledge base {kb_id}: {e}")
        return False

def search_knowledge_base(kb_id, query, top_k=3):
    """Search a specific knowledge base"""
    try:
        kb_folder = f"app/knowledge_bases/{kb_id}"
        index_path = f"{kb_folder}/index.faiss"
        chunks_path = f"{kb_folder}/chunks.pkl"
        
        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
            return []
        
        # Load index and chunks
        index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            chunks = pickle.load(f)
        
        # Create query embedding
        response = client.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        query_embedding = np.array(response.data[0].embedding, dtype="float32").reshape(1, -1)
        
        # Search
        distances, indices = index.search(query_embedding, top_k)
        results = [chunks[i] for i in indices[0] if i < len(chunks)]
        
        return results
        
    except Exception as e:
        print(f"Error searching knowledge base {kb_id}: {e}")
        return []