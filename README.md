# Logcat Analyzer with RAG and AI Chat

This project is a FastAPI web application for analyzing Android logcat logs, with advanced features:
- Multithreaded logcat error analysis (focus on fastrpc errors)
- AI-powered error explanations using OpenAI GPT-4
- Retrieval-Augmented Generation (RAG) module for context-aware answers from your C codebase and Confluence pages
- Modern chat UI with suggested next queries for deeper troubleshooting

## Features
- **Upload logcat files** and get detailed, AI-generated explanations for detected errors
- **Chat with the AI** about your logs, codebase, or Confluence docs, with context-aware answers
- **RAG module** ingests C source/header files and Confluence pages for retrieval
- **Next query suggestions** to guide your troubleshooting
- **Modern sidebar navigation** for easy access to all features
- **Add Knowledge Source page**: Add C codebase directories (including network paths) and Confluence spaces on demand, with a user-friendly UI

## Requirements
- Python 3.9+
- [OpenAI API key](https://platform.openai.com/account/api-keys) (set as `OPENAI_API_KEY`)
- (Optional) Confluence API credentials for RAG (set as environment variables)
- The following Python packages:
  - fastapi
  - uvicorn
  - openai
  - langchain
  - langchain-community
  - anthropic (optional, legacy)
  - jinja2

Install dependencies:
```sh
pip install fastapi uvicorn openai langchain langchain-community anthropic jinja2
```

## Environment Variables
Set these in your shell or a `.env` file:
- `OPENAI_API_KEY` (required)
- `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEY` (optional, for Confluence RAG)

## Project Structure
- `logcat_analyzer/main.py` — FastAPI backend, AI integration, chat, log analysis
- `logcat_analyzer/templates/` — Frontend HTML (Copilot-style UI)
- `rag_module/rag.py` — RAG module for codebase and Confluence ingestion/query

## Usage

1. **Start the app**:
   ```sh
   python main.py
   ```
2. **Access the web UI**:
   - Home: [http://localhost:8000](http://localhost:8000) or `http://<your-ip>:8000` from another device on your network
   - Use the sidebar to navigate between Home and Add Knowledge Source
3. **Add knowledge sources**:
   - Go to **Add Knowledge Source**
   - Select C Codebase and/or Confluence, fill in the required fields (network path, Confluence URL, credentials)
   - Click **Add Source(s)** to ingest new knowledge on demand
4. **Upload and analyze logcat files** on the Home page, then chat with the AI for context-aware help

## Sample Command to Run
From the `logcat_analyzer` directory:
```sh
python main.py
```

- To access from another PC on your network, use the host machine's IP address:
  - Example: `http://<your-pc-ip>:8000`
  - Make sure port 8000 is open in your firewall settings.

Then open your browser to [http://localhost:8000](http://localhost:8000) (or the above IP from a remote PC)

## Notes
- Update the `sources` path in `main.py` to point to your C codebase directory.
- Confluence integration is optional; if not configured, only codebase RAG is used.
- All API keys and credentials should be set via environment variables for security.

---
MIT License
