# AI Agent Question Generation System

A Flask-based application for generating high-quality multiple-choice questions using AI agents powered by OpenAI and Google Gemini. Designed specifically for creating CISSP-style exam questions with knowledge base integration, semantic repetition detection, and advanced reasoning controls.

## Features

- **Multi-Provider AI Support**: OpenAI (GPT-5.x, GPT-4.x) and Google Gemini models
- **Knowledge Base Integration**: Upload PDFs and DOCX files with FAISS vector search
- **Advanced Question Generation**: 
  - CISSP reasoning mode with two-stage retrieval
  - Semantic repetition detection using embeddings
  - Blueprint-based question diversity (domain, question type, reasoning mode)
- **Interactive Quiz Widget**: Embeddable quiz interface with instant feedback
- **Per-Agent Configuration**: Model selection, temperature, token limits, and custom parameters
- **Response Post-Processing**: Format validation, MCQ extraction, and quality controls
- **Chat Interface**: Generate questions with full conversation history

## Architecture

### Core Components

- **Agent System** (`app/agents/`): Multi-provider reply generation with CISSP reasoning controller
- **Knowledge Bases** (`app/knowledge_bases/`): Document processing, chunking, and FAISS indexing
- **Embedding System** (`app/embeddings/`): Vector search with OpenAI/Gemini embeddings
- **Response Processing** (`app/utils/response_processor.py`): Validation, repetition detection
- **Web Interface** (`app/web/`): Flask server with chat and quiz widgets

### Key Technologies

- **Backend**: Flask, Python 3.13+
- **AI Providers**: OpenAI API, Google Gemini API
- **Vector Search**: FAISS (Facebook AI Similarity Search)
- **Document Processing**: pypdf, python-docx, BeautifulSoup
- **Tokenization**: tiktoken

## Installation

### Prerequisites

- Python 3.13 or higher
- Windows, macOS, or Linux
- OpenAI API key and/or Google Gemini API key

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ai_agent
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**
   
   **Windows (PowerShell):**
   ```powershell
   venv\Scripts\Activate.ps1
   ```
   
   **Windows (CMD):**
   ```cmd
   venv\Scripts\activate.bat
   ```
   
   **macOS/Linux:**
   ```bash
   source venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure API keys**
   
   Copy example configuration files and add your API keys:
   
   **Windows (PowerShell):**
   ```powershell
   Copy-Item app\config\providers.example.json app\config\providers.json
   Copy-Item app\config\model_config.example.json app\config\model_config.json
   ```
   
   **macOS/Linux:**
   ```bash
   cp app/config/providers.example.json app/config/providers.json
   cp app/config/model_config.example.json app/config/model_config.json
   ```
   
   Then edit `app/config/providers.json` and add your API keys:
   ```json
   {
     "providers": {
       "openai": {
         "api_key": "sk-your-openai-key-here",
         "enabled": true
       },
       "gemini": {
         "api_key": "your-gemini-key-here",
         "enabled": true
       }
     }
   }
   ```
   
   **⚠️ Important**: These files are in `.gitignore` and should never be committed. See `SECURITY_NOTICE.md` for details.

## Running the Application

### Development Mode

**Windows (PowerShell):**
```powershell
venv\Scripts\python.exe -m flask run --host=0.0.0.0 --debug
```

**macOS/Linux:**
```bash
python -m flask run --host=0.0.0.0 --debug
```

The application will be available at:
- Local: `http://127.0.0.1:5000`
- Network: `http://<your-ip>:5000`

### Production Mode

For production deployment, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app.web.server:app"
```

## Usage

### 1. Configure API Keys

1. Navigate to **Settings** in the menu
2. Enter your OpenAI and/or Gemini API keys
3. Click **Save Configuration**

### 2. Create Knowledge Bases

1. Go to **Knowledge Bases** in the menu
2. Click **Add New Knowledge Base**
3. Upload PDF or DOCX files
4. Select embedding provider (OpenAI or Gemini)
5. Wait for processing to complete

### 3. Create an Agent

1. Navigate to **Agents**
2. Click **Create New Agent**
3. Configure:
   - **Basic Info**: Name, personality, style, prompt, formatting
   - **Knowledge Bases**: Select which KBs the agent can access
   - **Model Parameters**: Provider, model, temperature, token limits, etc.
   - **Post-Processing**: Enable MCQ validation, repetition detection
   - **CISSP Mode**: Enable blueprint-based question diversity (optional)

### 4. Generate Questions

**Via Chat Interface:**
1. Go to **Generate Questions** (home page)
2. Select your agent
3. Enter a prompt (e.g., "Generate a question about access control")
4. Review the generated question

**Via Quiz Widget:**
1. Go to **Agents**
2. Click **📝 Quiz Embed** next to your agent
3. Copy the embed code or use the direct link
4. Students can interact with the quiz and see instant feedback

## Configuration

### Agent Parameters

#### Model Parameters
- **Provider**: OpenAI or Gemini
- **Model**: Specific model variant (gpt-5.2, gemini-3-pro-preview, etc.)
- **Temperature** (0.0-2.0): Higher = more creative, Lower = more deterministic
- **Top P** (0.0-1.0): Nucleus sampling threshold
- **Frequency Penalty** (0.0-2.0): Reduces repetition of common phrases
- **Presence Penalty** (0.0-2.0): Encourages topic diversity
- **Max Output Tokens**: Maximum response length

#### Knowledge Base Settings
- **Max Knowledge Chunks**: Top N chunks to retrieve (default: 7)
- **Min Similarity Threshold**: Minimum cosine similarity for retrieval (0.0-1.0)
- **Conversation History Tokens**: Token budget for history (default: 1000)

#### Post-Processing
- **Enable MCQ Validation**: Extract and validate multiple-choice format
- **Enable Semantic Repetition Detection**: Compare question similarity
- **Semantic Similarity Threshold**: Trigger for repetition (default: 0.90)
- **Semantic History Depth**: Number of past questions to compare (default: 5)

#### CISSP Mode (Advanced)
- **Enable CISSP Mode**: Blueprint-based question diversity
- **Blueprint History Depth**: Rotation tracking (default: 8)
- Requires knowledge bases tagged as `cissp_type: "outline"` or `cissp_domain: "1-8"`

## Project Structure

```
ai_agent/
├── app/
│   ├── agents/          # Agent reply generation
│   ├── api/             # API layer for CRUD operations
│   ├── config/          # Configuration files (gitignored)
│   ├── data/            # Runtime data
│   ├── embeddings/      # Generated embeddings (gitignored)
│   ├── knowledge_bases/ # Uploaded documents (gitignored)
│   ├── models/          # Data models (Agent, ChatSession)
│   ├── utils/           # Utilities (KB processing, response processing)
│   └── web/             # Flask server and templates
│       ├── server.py
│       └── templates/   # HTML templates
├── venv/                # Virtual environment (gitignored)
├── .gitignore
├── README.md
├── requirements.txt
└── main.py
```

## Security Considerations

### Sensitive Files (Never Commit)
- `app/config/providers.json` - Contains API keys
- `app/config/agents.json` - User agent configurations
- `app/config/chat_sessions.json` - Conversation history
- `app/knowledge_bases/` - Uploaded documents
- `app/embeddings/` - Generated embeddings

All sensitive files are already in `.gitignore`.

### API Key Storage
- API keys are stored in `app/config/providers.json`
- File permissions should be restricted: `chmod 600 app/config/providers.json` (Unix)
- Consider using environment variables for production deployments

## Troubleshooting

### Issue: Module not found errors
**Solution**: Ensure virtual environment is activated and dependencies are installed:
```bash
pip install -r requirements.txt
```

### Issue: Windows console encoding errors
**Solution**: All emoji characters have been replaced with text prefixes. If you still see encoding issues, set:
```powershell
$env:PYTHONIOENCODING = "utf-8"
```

### Issue: Quiz generation returns incomplete JSON
**Solution**: Increase agent's `max_output_tokens`. Quiz generation automatically allocates `count * 400 + 200` tokens minimum.

### Issue: Knowledge base retrieval returns no results
**Solution**: 
- Check `min_similarity_threshold` (lower it if too strict)
- Verify knowledge base was processed successfully
- Ensure agent has access to the knowledge base

### Issue: Flask context errors
**Solution**: All Flask `g` object accesses are wrapped in try/except blocks. If you see context errors, ensure you're calling functions within a Flask request context or application context.

## Development

### Running Tests
```bash
pytest tests/
```

### Code Style
The project follows PEP 8 guidelines with:
- 4 spaces for indentation
- Maximum line length: 120 characters
- Type hints where applicable

### Adding a New AI Provider

1. Create client in `app/utils/` (e.g., `anthropic_client.py`)
2. Add provider config to `app/config/provider_config.py`
3. Update `_generate_with_<provider>()` in `app/agents/agent.py`
4. Add provider option in `app/web/templates/agents.html`

## License

[Specify your license here]

## Support

For issues, questions, or contributions, please [specify contact method or issue tracker].

## Acknowledgments

- OpenAI for GPT models and embeddings
- Google for Gemini API
- Facebook AI Research for FAISS
- Flask community
