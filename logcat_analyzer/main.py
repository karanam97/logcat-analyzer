from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import openai
import sys
import os

# Add parent directory to sys.path to fix ModuleNotFoundError
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rag_module.rag import RAGKnowledgeBase

import uvicorn
import threading
import anthropic

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Initialize RAGKnowledgeBase (configure sources and Confluence as needed)
rag = RAGKnowledgeBase(
    sources=["../path/to/your/c/codebase"],  # Update this path as needed
    confluence_config={
        "url": os.getenv("CONFLUENCE_URL"),
        "username": os.getenv("CONFLUENCE_USERNAME"),
        "api_token": os.getenv("CONFLUENCE_API_TOKEN"),
        "space_key": os.getenv("CONFLUENCE_SPACE_KEY"),
        # Optionally: "page_ids": [...], "cql": "..."
    } if os.getenv("CONFLUENCE_URL") else None
)


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Chat page
@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


# Store AI explanations in memory for demo purposes
ai_explanations = {}

@app.post("/analyze")
def analyze_logcat(file: UploadFile = File(...)):
    file_location = f"temp_{file.filename}"
    with open(file_location, "wb") as f:
        f.write(file.file.read())
    # Start analysis in a new thread, pass filename as key
    thread = threading.Thread(target=analyze_fastrpc_errors_with_ai, args=(file_location, file.filename))
    thread.start()
    return {"message": "Analysis started in background.", "filename": file.filename}


def analyze_fastrpc_errors_with_ai(file_path, filename):
    """
    Parse file for 'fastrpc' errors and use AI to explain them.
    Store results in ai_explanations dict.
    """
    explanations = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "fastrpc" in line.lower():
                explanation = get_ai_explanation(line.strip())
                explanations.append({"error": line.strip(), "ai_explanation": explanation})
    ai_explanations[filename] = explanations
    os.remove(file_path)

def get_ai_explanation(error_line: str) -> str:
    """
    Use OpenAI GPT-4 to explain the error, with RAG context from codebase and Confluence.
    """
    # Retrieve RAG context
    rag_context = rag.query(error_line)
    prompt = (
        f"You are an expert Android logcat and fastrpc error assistant. "
        f"Use the following context from the codebase and Confluence to explain the error.\n"
        f"Context:\n{rag_context}\n"
        f"Error: {error_line}\n"
        f"Explain the error in detail, including possible causes and solutions."
    )
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are an expert Android logcat and fastrpc error assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=350
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        return f"AI explanation unavailable: {e}"


# Endpoint to fetch AI explanations for a file
# Endpoint to fetch AI explanations for a file
@app.get("/results/{filename}")
def get_results(filename: str):
    return {"results": ai_explanations.get(filename, [])}



# Chat memory: store conversation history per session (simple demo, not persistent)
from fastapi import Body, Request
from fastapi.responses import JSONResponse


# In-memory chat history: {session_id: {chat_id: [messages]}}
import uuid
chat_histories = {}  # {session_id: {chat_id: [messages]}}

def get_session_id(request: Request) -> str:
    # Use client host+port as a simple session id (not secure, for demo only)
    return f"{request.client.host}:{request.client.port}"

def get_or_create_chat_id(session_id, chat_id=None):
    if session_id not in chat_histories:
        chat_histories[session_id] = {}
    if chat_id and chat_id in chat_histories[session_id]:
        return chat_id
    # Create new chat id
    new_id = str(uuid.uuid4())
    chat_histories[session_id][new_id] = []
    return new_id


@app.post("/chat")
async def chat_api(request: Request, message: dict = Body(...)):
    user_message = message.get("message", "")
    filename = message.get("filename")
    search_level = message.get("search_level")
    chat_id = message.get("chat_id")
    new_chat = message.get("new_chat", False)
    session_id = get_session_id(request)
    # Handle new chat
    if new_chat:
        chat_id = get_or_create_chat_id(session_id)
        return JSONResponse({"chat_id": chat_id, "history": []})
    # Use or create chat_id
    chat_id = get_or_create_chat_id(session_id, chat_id)
    history = chat_histories[session_id][chat_id]
    if not user_message.strip():
        return JSONResponse({"reply": "Please enter a message.", "chat_id": chat_id, "history": history})
    # If user uploaded a file, add its errors/AI explanations to context
    if filename and filename in ai_explanations:
        error_context = "\n".join([
            f"Error: {item['error']}\nAI: {item['ai_explanation']}" for item in ai_explanations[filename]
        ])
        if error_context:
            history.append({"role": "system", "content": f"Here are the errors and explanations from the uploaded logcat file:\n{error_context}"})
    # Add user message to history
    history.append({"role": "user", "content": user_message})
    reply, next_query = await get_ai_chat_response_with_memory(history, suggest_next_query=True, search_level=search_level)
    # Add AI reply to history
    history.append({"role": "assistant", "content": reply})
    # Limit history to last 20 messages
    chat_histories[session_id][chat_id] = history[-20:]
    return JSONResponse({"reply": reply, "next_query": next_query, "chat_id": chat_id, "history": chat_histories[session_id][chat_id]})

# Endpoint to list previous chats for the session
@app.get("/chats")
async def list_chats(request: Request):
    session_id = get_session_id(request)
    chats = chat_histories.get(session_id, {})
    return {"chats": list(chats.keys())}

# Endpoint to get a specific chat history
@app.get("/chat/{chat_id}")
async def get_chat(request: Request, chat_id: str):
    session_id = get_session_id(request)
    chats = chat_histories.get(session_id, {})
    history = chats.get(chat_id, [])
    return {"chat_id": chat_id, "history": history}


# --- Enhanced: Support for different search levels ---
from enum import Enum

class SearchLevel(str, Enum):
    QUICK = "quick"      # Fast, shallow search (default)
    STANDARD = "standard" # Standard, more context
    DEEP = "deep"        # Deep research, maximum context

def get_search_level_from_history(history, override=None):
    """
    Detects if the user requested a specific search level in their last message, or uses override if provided.
    Returns a SearchLevel value.
    """
    if override:
        if override == "deep":
            return SearchLevel.DEEP
        elif override == "quick":
            return SearchLevel.QUICK
        else:
            return SearchLevel.STANDARD
    user_message = next((msg['content'] for msg in reversed(history) if msg['role'] == 'user'), "")
    if "deep research" in user_message.lower():
        return SearchLevel.DEEP
    elif "standard search" in user_message.lower() or "standard" in user_message.lower():
        return SearchLevel.STANDARD
    elif "quick search" in user_message.lower() or "quick" in user_message.lower():
        return SearchLevel.QUICK
    return SearchLevel.STANDARD  # Default to standard

async def get_ai_chat_response_with_memory(history, suggest_next_query=False, search_level=None):
    """
    Use OpenAI GPT-4 for chat, with RAG context if available. Optionally, suggest a next query for the user.
    Supports different search levels: quick, standard, deep.
    Returns (reply, next_query) if suggest_next_query else just reply.
    """
    system_prompt = "You are an expert Android logcat and fastrpc error assistant. Answer user questions helpfully and use previous context if relevant."
    user_message = next((msg['content'] for msg in reversed(history) if msg['role'] == 'user'), None)
    level = get_search_level_from_history(history, override=search_level)
    # Adjust RAG context depth based on search level
    if level == SearchLevel.DEEP:
        rag_context = rag.query(user_message, depth="deep") if user_message else ""
    elif level == SearchLevel.QUICK:
        rag_context = rag.query(user_message, depth="quick") if user_message else ""
    else:
        rag_context = rag.query(user_message, depth="standard") if user_message else ""
    prompt = system_prompt + f"\n[Search Level: {level.value}]\n"
    if rag_context:
        prompt += f"[RAG Context]:\n{rag_context}\n"
    for msg in history:
        if msg["role"] == "user":
            prompt += f"User: {msg['content']}\n"
        elif msg["role"] == "assistant":
            prompt += f"Assistant: {msg['content']}\n"
        elif msg["role"] == "system":
            prompt += f"[Context]: {msg['content']}\n"
    prompt += "Assistant:"
    if suggest_next_query:
        prompt += "\n\nAfter your answer, suggest a relevant next question the user could ask to further investigate or resolve their issue. Format your suggestion as: NEXT QUERY: <your suggestion>"
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": prompt}],
            max_tokens=400
        )
        full_reply = response.choices[0].message['content'].strip()
        next_query = None
        if suggest_next_query:
            import re
            match = re.search(r'NEXT QUERY:(.*)', full_reply, re.IGNORECASE | re.DOTALL)
            if match:
                reply = full_reply[:match.start()].strip()
                next_query = match.group(1).strip()
            else:
                reply = full_reply
        else:
            reply = full_reply
        return (reply, next_query) if suggest_next_query else reply
    except Exception as e:
        if suggest_next_query:
            return (f"AI unavailable: {e}", None)
        return f"AI unavailable: {e}"

import socket

def get_local_ip():
    """Get the local IP address of the machine (cross-platform)."""
    import platform
    ip = '127.0.0.1'
    try:
        if platform.system().lower() == 'windows':
            # Windows: use socket trick
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
            finally:
                s.close()
        else:
            # Linux/Unix: try hostname -I, fallback to socket
            import subprocess
            try:
                ip_out = subprocess.check_output(['hostname', '-I']).decode().split()
                # Take the first non-localhost IPv4
                ip = next((x for x in ip_out if not x.startswith('127.') and '.' in x), ip)
            except Exception:
                # Fallback to socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(('10.255.255.255', 1))
                    ip = s.getsockname()[0]
                finally:
                    s.close()
    except Exception:
        pass
    return ip

@app.get("/add-knowledge", response_class=HTMLResponse)
def add_knowledge_page(request: Request):
    return templates.TemplateResponse("add_knowledge.html", {"request": request})

@app.post("/add-knowledge")
def add_knowledge_api(data: dict):
    source_type = data.get("type")
    if source_type == "codebase":
        path = data.get("path")
        if not path or not os.path.isdir(path):
            return {"message": "Invalid or missing codebase directory path."}
        rag.sources.append(path)
        rag._ingest_sources()
        return {"message": f"Codebase directory '{path}' added and ingested."}
    elif source_type == "confluence":
        url = data.get("url")
        username = data.get("username")
        api_token = data.get("api_token")
        space_key = data.get("space_key")
        if not all([url, username, api_token, space_key]):
            return {"message": "Missing Confluence configuration fields."}
        conf_cfg = {
            "url": url,
            "username": username,
            "api_token": api_token,
            "space_key": space_key
        }
        rag.confluence_config = conf_cfg
        rag._ingest_confluence()
        return {"message": f"Confluence space '{space_key}' added and ingested."}
    else:
        return {"message": "Unknown knowledge source type."}

if __name__ == "__main__":
    ip = get_local_ip()
    print(f"\nApp running! Access it locally at: http://localhost:8000\n" 
          f"Or from your network at: http://{ip}:8000\n")
    # Listen on all interfaces so remote PCs can access
    uvicorn.run(app, host="0.0.0.0", port=8000)
