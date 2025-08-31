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
import time

load_dotenv()

# Initialize OpenAI client with API key from config
def _get_openai_client():
    """Get OpenAI client with proper API key"""
    try:
        from app.config.api_config import get_openai_api_key
        api_key = get_openai_api_key()
        if not api_key:
            raise ValueError("No API key configured")
        return OpenAI(api_key=api_key)
    except ImportError:
        raise ValueError("API config not available")

# Don't create client at import time - create when needed

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
            response = _get_openai_client().embeddings.create(
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

def generate_ai_summary(text, title="", source_type="document"):
    """Generate an AI summary/description of the knowledge base content"""
    try:
        # Truncate text if too long (keep first 8000 characters for context)
        truncated_text = text[:8000] if len(text) > 8000 else text
        
        prompt = f"""Analyze the following {source_type} content and write a concise, helpful summary that describes what information is contained within. This summary will be used as a description to help AI agents understand what knowledge is available in this source.

Title: {title}
Content Type: {source_type}

Content:
{truncated_text}

Write a 2-3 sentence summary that describes:
1. What type of information this contains
2. Key topics or subjects covered
3. How this information might be useful for answering questions

Keep it concise but informative. Focus on the practical value and scope of the content."""

        response = _get_openai_client().chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that creates concise, informative summaries of knowledge base content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content.strip()
        return summary
        
    except Exception as e:
        print(f"Error generating AI summary: {e}")
        return f"Knowledge base containing {source_type} content related to {title}."

# Legacy web scraping functions removed - now using direct OpenAI approach for better results

def find_nearby_locations_with_openai(location_name):
    """Use OpenAI directly to find nearby locations - more reliable than web scraping"""
    try:
        print(f"🔍 Using OpenAI to find locations near: {location_name}")
        
        prompt = f"""Can I get a list of cities, towns, and neighborhoods near {location_name}? Make it comma-separated, not a vertical list. No less than 15, no more than 25.

Include places that are:
- Within reasonable commuting distance (20-30 miles)
- Cities, towns, neighborhoods, boroughs, or well-known areas
- Places people might live or work if they're considering events in {location_name}

Focus on actual place names that people would recognize and use when describing where they live or work."""

        response = _get_openai_client().chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a geographic assistant. Provide accurate, comma-separated lists of nearby locations. Only return the list, no explanations or additional text."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.1
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Parse the comma-separated response
        if ai_response:
            locations = [loc.strip() for loc in ai_response.split(',') if loc.strip()]
            # Filter out the original location to avoid duplicates
            locations = [loc for loc in locations if loc.lower() != location_name.lower()]
            
            if locations:
                print(f"✅ Found {len(locations)} nearby locations for {location_name}: {', '.join(locations[:5])}...")
                return locations[:25]  # Limit to 25 as requested
            else:
                print(f"❌ No nearby locations found for {location_name}")
                return []
        
        return []
        
    except Exception as e:
        print(f"Error finding nearby locations with OpenAI for {location_name}: {e}")
        return []

def find_nearby_locations(location_name):
    """Complete pipeline to find nearby locations using OpenAI directly"""
    try:
        # Use the new OpenAI-based approach
        nearby_locations = find_nearby_locations_with_openai(location_name)
        
        # Add small delay to be respectful to API limits
        time.sleep(0.5)
        
        return nearby_locations
        
    except Exception as e:
        print(f"Error finding nearby locations for {location_name}: {e}")
        return []

def extract_unique_locations_from_events(event_data):
    """Extract unique location names from event data"""
    try:
        locations = set()
        
        # Handle both list and single event
        events = event_data if isinstance(event_data, list) else [event_data]
        
        for event in events:
            # Try multiple possible location field names
            location = (event.get('Location') or 
                       event.get('location') or 
                       event.get('venue') or
                       event.get('Venue') or
                       event.get('city') or
                       event.get('City'))
            
            if location and isinstance(location, str):
                # Clean and normalize location name
                clean_location = location.strip()
                if clean_location and len(clean_location) > 2:  # Avoid single letters or very short strings
                    locations.add(clean_location)
        
        return list(locations)
        
    except Exception as e:
        print(f"Error extracting locations from event data: {e}")
        return []

def enhance_event_kb_description(kb_id, primary_locations, nearby_areas):
    """Automatically enhance KB description with location information"""
    try:
        from app.config.knowledge_config import load_knowledge_config, save_knowledge_config
        
        if not primary_locations:
            return False
        
        # Create enhanced description
        primary_text = ', '.join(primary_locations)
        
        if nearby_areas:
            nearby_text = ', '.join(nearby_areas)
            enhanced_description = f"Events in {primary_text}. This includes areas like {nearby_text}"
        else:
            enhanced_description = f"Events in {primary_text}"
        
        # Update the knowledge base configuration
        config = load_knowledge_config()
        kb_found = False
        
        for kb in config.get('knowledge_bases', []):
            if kb.get('id') == kb_id:
                # Preserve existing description if it's not auto-generated
                existing_desc = kb.get('description', '')
                if not existing_desc or existing_desc.startswith('Events in '):
                    kb['description'] = enhanced_description
                    kb_found = True
                    print(f"✅ Updated KB description for {kb_id}: {enhanced_description}")
                else:
                    # Append to existing description
                    kb['description'] = f"{existing_desc}. {enhanced_description}"
                    kb_found = True
                    print(f"✅ Enhanced existing KB description for {kb_id}")
                break
        
        if kb_found:
            save_knowledge_config(config)
            return True
        else:
            print(f"❌ Knowledge base {kb_id} not found for description update")
            return False
            
    except Exception as e:
        print(f"Error enhancing KB description for {kb_id}: {e}")
        return False

def process_knowledge_base(kb_id, kb_type, source_path, generate_summary=False):
    """Process a knowledge base and create embeddings"""
    try:
        # Check if this is an event knowledge base
        from app.config.knowledge_config import load_knowledge_config
        config = load_knowledge_config()
        is_event_kb = False
        kb_info = None
        
        for kb in config.get('knowledge_bases', []):
            if kb.get('id') == kb_id:
                is_event_kb = kb.get('is_events', False)
                kb_info = kb
                break
        
        # Extract text based on type
        if kb_type == "file":
            if source_path.lower().endswith('.docx'):
                text = extract_text_from_docx(source_path)
            elif source_path.lower().endswith('.pdf'):
                text = extract_text_from_pdf(source_path)
            else:
                print(f"Unsupported file type: {source_path}")
                return False, None
        elif kb_type == "url":
            text = fetch_content_from_url(source_path)
        else:
            print(f"Unsupported knowledge base type: {kb_type}")
            return False, None
        
        if not text:
            print(f"No text extracted from {source_path}")
            return False, None
        
        # Handle event knowledge bases - discover nearby locations
        if is_event_kb and kb_type == "url":
            try:
                print(f"🎯 Processing event knowledge base: {kb_id}")
                
                # Try to parse as JSON to extract event data
                try:
                    event_data = json.loads(text)
                    
                    # Extract unique locations from events
                    primary_locations = extract_unique_locations_from_events(event_data)
                    
                    if primary_locations:
                        print(f"📍 Found {len(primary_locations)} primary locations: {', '.join(primary_locations)}")
                        
                        # Discover nearby areas for each location
                        all_nearby_areas = []
                        for location in primary_locations:
                            nearby = find_nearby_locations(location)
                            all_nearby_areas.extend(nearby)
                        
                        # Remove duplicates and limit results
                        unique_nearby = list(dict.fromkeys(all_nearby_areas))[:20]  # Keep order, remove dupes, limit to 20
                        
                        if unique_nearby:
                            print(f"🗺️ Discovered {len(unique_nearby)} nearby areas")
                            # Update KB description with location information
                            enhance_event_kb_description(kb_id, primary_locations, unique_nearby)
                        else:
                            print("❌ No nearby areas discovered")
                    else:
                        print("❌ No locations found in event data")
                        
                except json.JSONDecodeError:
                    print("⚠️ Event KB content is not valid JSON, skipping location discovery")
                    
            except Exception as e:
                print(f"⚠️ Error during event location discovery for {kb_id}: {e}")
                # Continue with normal processing even if location discovery fails
        
        # Generate AI summary if requested
        ai_summary = None
        if generate_summary:
            title = kb_info.get('title', '') if kb_info else ""
            ai_summary = generate_ai_summary(text, title, kb_type)
        
        # Chunk the text
        chunks = chunk_text(text)
        if not chunks:
            print(f"No chunks created from {source_path}")
            return False, ai_summary
        
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
        return True, ai_summary
        
    except Exception as e:
        print(f"Error processing knowledge base {kb_id}: {e}")
        return False, None

def discover_locations_for_event_kb(kb_id):
    """Manually trigger location discovery for an existing event knowledge base"""
    try:
        from app.config.knowledge_config import load_knowledge_config
        
        config = load_knowledge_config()
        kb_info = None
        
        # Find the knowledge base
        for kb in config.get('knowledge_bases', []):
            if kb.get('id') == kb_id:
                kb_info = kb
                break
        
        if not kb_info:
            print(f"❌ Knowledge base {kb_id} not found")
            return False
        
        if not kb_info.get('is_events', False):
            print(f"❌ Knowledge base {kb_id} is not marked as an event KB")
            return False
        
        if kb_info.get('type') != 'url':
            print(f"❌ Knowledge base {kb_id} is not a URL type (location discovery only works for URL event sources)")
            return False
        
        # Fetch the event data
        source_url = kb_info.get('source')
        if not source_url:
            print(f"❌ No source URL found for KB {kb_id}")
            return False
        
        print(f"🔍 Discovering locations for event KB: {kb_info.get('title', kb_id)}")
        
        # Fetch content from URL
        try:
            response = requests.get(source_url)
            response.raise_for_status()
            event_data = response.json()
        except Exception as e:
            print(f"❌ Error fetching event data from {source_url}: {e}")
            return False
        
        # Extract locations and discover nearby areas
        primary_locations = extract_unique_locations_from_events(event_data)
        
        if not primary_locations:
            print("❌ No locations found in event data")
            return False
        
        print(f"📍 Found {len(primary_locations)} primary locations: {', '.join(primary_locations)}")
        
        # Discover nearby areas
        all_nearby_areas = []
        for location in primary_locations:
            nearby = find_nearby_locations(location)
            all_nearby_areas.extend(nearby)
        
        # Remove duplicates and limit results
        unique_nearby = list(dict.fromkeys(all_nearby_areas))[:20]
        
        if unique_nearby:
            print(f"🗺️ Discovered {len(unique_nearby)} nearby areas")
            # Update KB description
            success = enhance_event_kb_description(kb_id, primary_locations, unique_nearby)
            return success
        else:
            print("❌ No nearby areas discovered")
            return False
            
    except Exception as e:
        print(f"Error discovering locations for KB {kb_id}: {e}")
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
        response = _get_openai_client().embeddings.create(
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