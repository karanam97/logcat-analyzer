from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import uvicorn
import os
import threading
import anthropic

app = FastAPI()
templates = Jinja2Templates(directory="templates")


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
    Call Anthropic Claude API to get an explanation for the error line.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = f"Explain the following Android fastrpc error in detail, including possible causes and solutions.\nError: {error_line}"
    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",  # Claude 3 Opus is the most capable, you can use 'claude-3-sonnet' for faster/cheaper
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
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

# In-memory chat history: {session_id: [ {"role": "user"|"assistant", "content": str}, ... ] }
chat_histories = {}

def get_session_id(request: Request) -> str:
    # Use client host+port as a simple session id (not secure, for demo only)
    return f"{request.client.host}:{request.client.port}"

@app.post("/chat")
async def chat_api(request: Request, message: dict = Body(...)):
    user_message = message.get("message", "")
    filename = message.get("filename")
    if not user_message.strip():
        return JSONResponse({"reply": "Please enter a message."})
    session_id = get_session_id(request)
    history = chat_histories.setdefault(session_id, [])
    # If user uploaded a file, add its errors/AI explanations to context
    if filename and filename in ai_explanations:
        # Add a summary of errors as context for the AI
        error_context = "\n".join([
            f"Error: {item['error']}\nAI: {item['ai_explanation']}" for item in ai_explanations[filename]
        ])
        if error_context:
            history.append({"role": "system", "content": f"Here are the errors and explanations from the uploaded logcat file:\n{error_context}"})
    # Add user message to history
    history.append({"role": "user", "content": user_message})
    reply = await get_ai_chat_response_with_memory(history)
    # Add AI reply to history
    history.append({"role": "assistant", "content": reply})
    # Limit history to last 10 messages
    chat_histories[session_id] = history[-10:]
    return JSONResponse({"reply": reply})

async def get_ai_chat_response_with_memory(history) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    # Build a single prompt from the history
    system_prompt = "You are an expert Android logcat and fastrpc error assistant. Answer user questions helpfully and use previous context if relevant."
    prompt = system_prompt + "\n"
    for msg in history:
        if msg["role"] == "user":
            prompt += f"User: {msg['content']}\n"
        elif msg["role"] == "assistant":
            prompt += f"Assistant: {msg['content']}\n"
        elif msg["role"] == "system":
            prompt += f"[Context]: {msg['content']}\n"
    prompt += "Assistant:"
    try:
        response = await client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"AI unavailable: {e}"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
