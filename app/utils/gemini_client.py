"""
Gemini API client wrapper using official google-genai SDK.
Provides unified interface matching OpenAI pattern for easier integration.
"""

from typing import List, Dict, Optional
try:
    from google import genai
except ImportError:
    genai = None
    print("⚠️ google-genai not installed. Install with: pip install google-genai")

from app.config.provider_config import get_provider_api_key

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        if genai is None:
            raise ImportError("google-genai package not installed")
        
        self.api_key = api_key or get_provider_api_key("gemini")
        if not self.api_key:
            raise ValueError("No Gemini API key configured")
        
        # Create client with API key
        self.client = genai.Client(api_key=self.api_key)
    
    def generate_content(self, model: str, messages: List[Dict], 
                        temperature: float = 0.9, max_tokens: int = 1000, **kwargs):
        """
        Generate content using Gemini API with official google-genai SDK.
        
        Args:
            model: Model name (e.g., "gemini-2.5-flash", "gemini-3-pro")
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            **kwargs: Additional parameters
            
        Returns:
            GeminiResponse object with .text and .content attributes
        """
        # Extract system instruction and build content
        system_instruction = None
        user_content = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                user_content.append(msg["content"])
            elif msg["role"] == "assistant":
                # For multi-turn conversations
                user_content.append(f"[Previous Response]\n{msg['content']}\n")
        
        # Combine user content
        contents = "\n".join(user_content)
        
        try:
            # Call the new API (config parameters not yet supported in this SDK version)
            response = self.client.models.generate_content(
                model=model,
                contents=contents
            )
            
            # Extract text from response
            return GeminiResponse(response.text)
        except Exception as e:
            print(f"⚠️ Gemini generation error: {e}")
            raise
    
    def embed_content(self, model: str, content: str):
        """
        Generate embeddings using Gemini with official google-genai SDK.
        
        Args:
            model: Embedding model name (e.g., "text-embedding-004")
            content: Text to embed
            
        Returns:
            GeminiEmbeddingResponse with .data attribute
        """
        try:
            # Call the new embeddings API
            result = self.client.models.embed_content(
                model=model,
                contents=content
            )
            
            # Extract embedding from response
            # The new SDK returns embeddings in a different format
            if hasattr(result, 'embeddings') and len(result.embeddings) > 0:
                embedding = result.embeddings[0].values
            elif hasattr(result, 'embedding'):
                embedding = result.embedding
            else:
                # Fallback: try to access as dict
                embedding = result.get('embedding', [])
            
            return GeminiEmbeddingResponse(embedding)
        except Exception as e:
            print(f"⚠️ Gemini embedding error: {e}")
            raise

class GeminiResponse:
    """Response wrapper to match OpenAI response structure"""
    def __init__(self, text: str):
        self.text = text
        self.content = text
        
    def __str__(self):
        return self.text

class GeminiEmbeddingResponse:
    """Embedding response wrapper to match OpenAI embedding structure"""
    def __init__(self, embedding: List[float]):
        self.data = [{"embedding": embedding}]
