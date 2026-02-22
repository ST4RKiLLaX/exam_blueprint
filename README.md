# ExamBlueprint

AI-powered certification question generation platform. Transform your study materials and knowledge bases into unlimited, high-quality multiple-choice questions with intelligent domain rotation, reasoning diversity, and semantic duplicate detection. Designed for certification exam prep (CISSP, CompTIA, CISM, and more) with support for OpenAI and Google Gemini models.

## Features

- **Secure Authentication**: User management with role-based access control (Admin/User)
  - Argon2id password hashing
  - Account lockout protection
  - Audit logging for admin actions
  - Session management with Flask-Security-Too
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
- **Authentication**: Flask-Security-Too, Flask-SQLAlchemy, Argon2id
- **AI Providers**: OpenAI API, Google Gemini API
- **Vector Search**: FAISS (Facebook AI Similarity Search)
- **Document Processing**: pypdf, python-docx, BeautifulSoup
- **Tokenization**: tiktoken
- **Security**: Rate limiting, account lockout, audit logging, proxy headers support

## Installation

### Prerequisites

- Python 3.11+ (Python 3.13 recommended)
- Windows, macOS, or Linux
- OpenAI API key and/or Google Gemini API key

### Python 3.13 Installation (Linux/Debian)

If Python 3.13 is not available or lacks SQLite support, compile it with all required libraries:

#### Install Build Dependencies

```bash
apt-get update
apt-get install -y \
    build-essential \
    libsqlite3-dev \
    libssl-dev \
    libffi-dev \
    libbz2-dev \
    libreadline-dev \
    libncurses5-dev \
    libgdbm-dev \
    liblzma-dev \
    zlib1g-dev \
    tk-dev \
    uuid-dev
```

#### Compile Python 3.13

```bash
cd /usr/src
wget https://www.python.org/ftp/python/3.13.1/Python-3.13.1.tgz
tar xzf Python-3.13.1.tgz
cd Python-3.13.1

# Configure with optimizations
./configure --enable-optimizations --with-lto

# Compile (using all CPU cores)
make -j $(nproc)

# Install (altinstall keeps system Python intact)
make altinstall
```

#### Verify SQLite Support

```bash
python3.13 -c "import sqlite3; print(f'SQLite version: {sqlite3.sqlite_version}')"
```

If this prints a version number, Python 3.13 is correctly configured.

**Alternative**: Use your system's Python 3.11/3.12 which includes SQLite support by default:
```bash
python3 --version  # Check system Python version
```

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd exam_blueprint
   ```

2. **Create a virtual environment**
   
   **Windows:**
   ```bash
   python -m venv venv
   ```
   
   **Linux/macOS:**
   ```bash
   # Use python3.13 if compiled, or python3 for system version
   python3.13 -m venv venv
   # OR
   python3 -m venv venv
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

5. **Create local config files (no manual key edits required)**
   
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
   
   Then start the app and set API keys from the **Settings** page in the UI.
   No manual editing of JSON key files is required.
   
   **⚠️ Important**: Local config files are in `.gitignore` and should never be committed.
   See `SECURITY_NOTICE.md` for details.

## Running the Application

### Development Mode

**Windows (PowerShell):**
```powershell
venv\Scripts\python.exe -m flask run --host=0.0.0.0 --debug
```

**macOS/Linux:**

The Flask app is located in `app/web/server.py`, so you must tell Flask where to find it:

```bash
# Set Flask app location
export FLASK_APP=app.web.server

# Run the server
python -m flask run --host=0.0.0.0 --debug
```

**Or use the --app flag directly:**
```bash
python -m flask --app app.web.server run --host=0.0.0.0 --debug
```

**Create a launch script (optional):**

Save as `run.sh`:
```bash
#!/bin/bash
export FLASK_APP=app.web.server
python3 -m flask run --host=0.0.0.0 --debug
```

Then run:
```bash
chmod +x run.sh
./run.sh
```

The application will be available at:
- Local: `http://127.0.0.1:5000`
- Network: `http://<your-ip>:5000`

### First-Time Login

On the first run, the application will automatically:
1. Create the user database (`app/config/users.db`)
2. Generate a default admin account
3. Print the credentials to the console:

```
============================================================
INITIAL ADMIN ACCOUNT CREATED
============================================================
Email:    admin@example.com
Password: [randomly-generated-password]
============================================================
PLEASE SAVE THESE CREDENTIALS AND CHANGE PASSWORD IMMEDIATELY
============================================================
```

**⚠️ Important**: Save these credentials immediately. The password is only shown once during first run.

**Changing Your Password:**
1. Log in with the default admin account
2. Navigate to **Users** (admin menu)
3. Click **Reset Password** next to your account
4. Enter your new password

### Production Mode

For production deployment, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app.web.server:app"
```

## Usage

### 1. User Management (Admin Only)

After logging in as admin, you can manage users:

**Add New Users:**
1. Navigate to **Users** in the menu
2. Click **Add New User**
3. Enter email, password, and role (User or Admin)

**Manage Existing Users:**
- **Edit Email**: Change a user's email address
- **Reset Password**: Generate a new password for any user
- **Activate/Deactivate**: Enable or disable user accounts
- **Delete**: Remove users from the system

**View Audit Log:**
- All administrative actions are logged with timestamp, admin email, action type, and IP address
- Access the audit log at the bottom of the Users page

### 2. Configure API Keys (Admin Only)

1. Navigate to **Settings** in the menu
2. Enter your OpenAI and/or Gemini API keys
3. Click **Save Configuration**
4. Keys are saved through the application and encrypted at rest

### 3. Create Knowledge Bases

1. Go to **Knowledge Bases** in the menu
2. Click **Add New Knowledge Base**
3. Upload PDF or DOCX files
4. Select embedding provider (OpenAI or Gemini)
5. Wait for processing to complete

### 4. Create an Agent

1. Navigate to **Agents**
2. Click **Create New Agent**
3. Configure:
   - **Basic Info**: Name, personality, style, prompt, formatting
   - **Knowledge Bases**: Select which KBs the agent can access
   - **Model Parameters**: Provider, model, temperature, token limits, etc.
   - **Post-Processing**: Enable MCQ validation, repetition detection
   - **CISSP Mode**: Enable blueprint-based question diversity (optional)

### 5. Generate Questions

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
exam_blueprint/
├── app/
│   ├── agents/          # AI agent reply generation
│   ├── api/             # API layer for CRUD operations
│   ├── config/          # Configuration files (gitignored)
│   │   └── users.db     # User database (SQLite, gitignored)
│   ├── data/            # Runtime data
│   ├── embeddings/      # Generated embeddings (gitignored)
│   ├── knowledge_bases/ # Uploaded documents (gitignored)
│   ├── models/          # Data models (Agent, ChatSession, User, AuditLog)
│   │   ├── agent.py
│   │   ├── user.py      # User and Role models
│   │   └── audit_log.py # Admin action audit logging
│   ├── utils/           # Utilities (KB processing, response processing)
│   └── web/             # Flask server and templates
│       ├── server.py
│       └── templates/   # HTML templates
│           ├── security/ # Authentication templates
│           │   └── login_user.html
│           └── users.html # User management
├── venv/                # Virtual environment (gitignored)
├── .gitignore
├── README.md
├── requirements.txt
├── SECURITY_NOTICE.md
└── main.py
```

## Security Considerations

### Sensitive Files (Never Commit)
- `app/config/api_config.json` - Contains encrypted API keys and key metadata
- `app/config/providers.json` - Provider metadata (and legacy plaintext keys before migration)
- `app/config/users.db` - User database with hashed passwords
- `app/config/agents.json` - User agent configurations
- `app/config/chat_sessions.json` - Conversation history
- `app/knowledge_bases/` - Uploaded documents
- `app/embeddings/` - Generated embeddings

All sensitive files are already in `.gitignore`.

### Authentication Security
- **Password Hashing**: Argon2id algorithm (OWASP recommended)
- **Account Lockout**: Automatic lockout after 5 failed login attempts (15-minute cooldown)
- **Session Management**: Flask-Security-Too with secure session cookies
- **Audit Logging**: All admin actions logged with timestamp, user, and IP address
- **Rate Limiting**: Flask-Limiter protects against brute force attacks
- **Role-Based Access**: Admin and User roles with granular permissions

### API Key Storage
- API keys are stored encrypted in `app/config/api_config.json`
- Encryption key is stored in `app/config/api_encryption.key`
- File permissions should be restricted (Unix):
  - `chmod 600 app/config/api_config.json`
  - `chmod 600 app/config/api_encryption.key`
- Consider using environment variables for production deployments

### Reverse Proxy Support
- Application supports `X-Forwarded-For` and `X-Forwarded-Proto` headers
- Properly configured for deployment behind nginx, Apache, or cloud load balancers

## Troubleshooting

### Issue: "No module named '_sqlite3'" (Linux)
**Solution**: Python was compiled without SQLite support. You need to either:

1. **Recompile Python 3.13 with SQLite libraries** (see Installation section above)
2. **Use system Python** which includes SQLite by default:
   ```bash
   deactivate  # exit current venv
   rm -rf venv
   python3 -m venv venv  # Use system Python
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### Issue: "Failed to find Flask application or factory" (Linux)
**Solution**: Set the Flask app location:
```bash
export FLASK_APP=app.web.server
python -m flask run --host=0.0.0.0 --debug
```

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

### Issue: Cannot log in with initial password
**Solution**: 
- The password is only displayed once during first run in the console
- If you lost it, delete `app/config/users.db` and restart the server to regenerate
- Make sure you're copying the password exactly as shown (no extra spaces)

### Issue: Account locked after failed login attempts
**Solution**: 
- Accounts automatically lock after 5 failed login attempts
- Wait 15 minutes for automatic unlock, or
- Have another admin reset the password via the Users page

### Issue: Email validation error on user creation
**Solution**: 
- Email addresses must be valid format (e.g., `user@example.com`)
- Email addresses must be unique
- Local domains like `@localhost` are not accepted

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
