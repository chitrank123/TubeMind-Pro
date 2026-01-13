import os
import json
import jwt
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
import bcrypt

# --- MODULES ---
from database import init_db, get_db, VideoEmbedding, User, Session, ChatMessage
from graph_brain import app_graph

# --- LIBRARIES ---
from langchain_community.document_loaders import YoutubeLoader 
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder
from langchain_text_splitters import RecursiveCharacterTextSplitter
from groq import Groq
from ddgs import DDGS
from youtube_search import YoutubeSearch
from dotenv import load_dotenv
load_dotenv()
# --- CONFIG ---
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

# --- 1. SWAGGER UI SECURITY SETUP ---
app = FastAPI(
    title="TubeMind Pro", 
    version="3.1.0",
    swagger_ui_init_oauth={
        "clientId": "tubemind-client", 
        "clientSecret": "secret"
    }
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token") # Point to the token endpoint

# --- MODELS ---
print("⏳ Loading AI Models...")
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
print("✅ Models Ready!")

# --- AUTH HELPERS ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_from_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        return username
    except: return None

@app.on_event("startup")
async def on_startup():
    await init_db()

# --- REQUEST SCHEMAS ---
class AuthRequest(BaseModel):
    username: str
    password: str

class VideoRequest(BaseModel):
    url: str
    
class SessionRequest(BaseModel):
    video_id: str
    title: str
    username: str

# --- AUTH ENDPOINTS ---
# Added form-data support for Swagger UI's "Authorize" button
@app.post("/auth/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.username == form_data.username))
    user = res.scalars().first()
    if not user or not bcrypt.checkpw(form_data.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username, "id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/register")
async def register(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.username == req.username))
    if res.scalars().first(): raise HTTPException(400, "Username taken")
    
    hashed = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt())
    hash_pw = hashed.decode('utf-8')
    user = User(username=req.username, password_hash=hash_pw)
    db.add(user)
    await db.commit()
    return {"status": "created"}

@app.post("/auth/login")
async def login(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.username == req.username))
    user = res.scalars().first()
    if not user or not bcrypt.checkpw(req.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(400, "Invalid credentials")
    
    token = create_access_token({"sub": user.username, "id": user.id})
    return {"access_token": token, "username": user.username}

# --- SESSION MANAGEMENT ---
@app.post("/api/session/create")
async def create_session(req: SessionRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.username == req.username))
    user = res.scalars().first()
    if not user: raise HTTPException(400, "User not found")
    
    new_session = Session(user_id=user.id, video_id=req.video_id, title=req.title)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return {"session_id": new_session.id}

@app.get("/api/sessions/{username}")
async def get_sessions(username: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.username == username))
    user = res.scalars().first()
    if not user: return []
    stmt = select(Session).where(Session.user_id == user.id).order_by(desc(Session.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()

@app.get("/api/history/{session_id}")
async def get_history(session_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    res = await db.execute(stmt)
    msgs = res.scalars().all()
    # Return simple dicts. 'meta' contains thinking steps if saved previously.
    return [{"role": m.role, "text": m.content, "meta": m.metadata_} for m in msgs]

# --- RAG UTILS ---
def get_video_id(url):
    if "v=" in url: return url.split("v=")[1].split("&")[0]
    return None

def format_timestamp(seconds):
    minutes = int(seconds // 60)
    remaining_sec = int(seconds % 60)
    return f"{minutes:02d}:{remaining_sec:02d}"

async def postgres_retrieval(db: AsyncSession, query: str, video_id: str):
    query_vec = embeddings.embed_query(query)
    stmt = select(VideoEmbedding).where(VideoEmbedding.video_id == video_id)\
           .order_by(VideoEmbedding.embedding.cosine_distance(query_vec)).limit(10)
    result = await db.execute(stmt)
    initial_docs = result.scalars().all()
    if not initial_docs: return ""

    pairs = [[query, doc.content] for doc in initial_docs]
    scores = reranker.predict(pairs)
    scored_docs = sorted(zip(initial_docs, scores), key=lambda x: x[1], reverse=True)
    top_docs = [doc for doc, score in scored_docs[:3]]
    return "\n".join([f"[Time: {format_timestamp(d.start_time)}] {d.content}" for d in top_docs])

async def generate_resources_on_load(text_sample):
    client = Groq()
    try:
        resp = client.chat.completions.create(messages=[{"role": "user", "content": f"Extract TOPIC (3 words). Transcript: {text_sample[:1000]}."}], model="llama-3.3-70b-versatile")
        topic = resp.choices[0].message.content.strip().replace('"', '')
    except: topic = "General"

    videos = []
    blogs = []
    try:
        yt_results = YoutubeSearch(f"{topic} tutorial", max_results=3).to_dict()
        videos = [{"title": v['title'], "link": f"https://www.youtube.com{v['url_suffix']}"} for v in yt_results]
    except: pass
    try:
        with DDGS() as ddgs:
            b_results = ddgs.text(f"{topic} tutorial (site:medium.com OR site:dev.to) -site:youtube.com", max_results=4)
            if b_results:
                for r in b_results:
                    if "youtube" not in r['href']: blogs.append({"title": r['title'], "link": r['href']})
    except: pass
    return {"topic": topic, "videos": videos, "blogs": blogs}

# --- WEBSOCKET WITH AUTH & HISTORY ---
@app.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket, 
    token: str = Query(...), 
    session_id: int = Query(...), 
    db: AsyncSession = Depends(get_db)
):
    await websocket.accept()
    
    username = get_current_user_from_token(token)
    if not username:
        await websocket.close(code=4001)
        return

    async for session in get_db(): db_session = session; break

    try:
        hist_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
        res = await db_session.execute(hist_stmt)
        history_objs = res.scalars().all()
        chat_history = [{"role": m.role, "content": m.content} for m in history_objs]

        while True:
            data = await websocket.receive_text()
            req = json.loads(data)
            user_msg = req.get("message")
            current_video_id = get_video_id(req.get("url", "")) 

            # Save User Message
            user_db_msg = ChatMessage(session_id=session_id, role="user", content=user_msg)
            db_session.add(user_db_msg)
            await db_session.commit()
            
            # Retrieval
            context = ""
            if current_video_id:
                # 2. EVENT: Retrieval Start
                await websocket.send_json({"type": "thought", "data": "🔎 Searching Knowledge Base..."})
                context = await postgres_retrieval(db_session, user_msg, current_video_id)

            # Graph State
            initial_state = {
                "query": user_msg, 
                "context": context, 
                "chat_history": chat_history,
                "next_step": "",
                "final_answer": "", 
                "reasoning": "", 
                "suggestions": [], 
                "metadata": {}
            }

            final_answer = ""
            suggestions = []
            final_meta = {}
            thoughts = [] # Accumulate thoughts here for DB

            if context: thoughts.append(f"🔎 Found relevant video context.")

            async for event in app_graph.astream(initial_state):
                for node_name, node_state in event.items():
                    if "reasoning" in node_state:
                         thought_text = f"⚙️ {node_name.upper()}: {node_state['reasoning']}"
                         thoughts.append(thought_text)
                         # 3. EVENT: Send individual thought to UI
                         await websocket.send_json({"type": "thought", "data": thought_text})
                    
                    if "final_answer" in node_state: final_answer = node_state["final_answer"]
                    if "suggestions" in node_state: suggestions = node_state["suggestions"]
                    if "metadata" in node_state: final_meta = node_state["metadata"]

            # Attach collected thoughts to metadata for persistence
            final_meta["thoughts"] = thoughts

            # Save AI Response
            ai_db_msg = ChatMessage(session_id=session_id, role="ai", content=final_answer, metadata_=final_meta)
            db_session.add(ai_db_msg)
            await db_session.commit()
            
            chat_history.append({"role": "user", "content": user_msg})
            chat_history.append({"role": "ai", "content": final_answer})

            await websocket.send_json({
                "type": "result", "data": final_answer, "suggestions": suggestions, "meta": final_meta
            })

    except WebSocketDisconnect: print("Client disconnected")

@app.post("/api/process")
async def process_video(request: VideoRequest, db: AsyncSession = Depends(get_db)):
    video_id = get_video_id(request.url)
    if not video_id: raise HTTPException(400, "Invalid URL")
    
    try:
        loader = YoutubeLoader.from_youtube_url(request.url, add_video_info=False)
        raw_docs = loader.load()
        full_text = " ".join([d.page_content for d in raw_docs])
    except Exception as e: raise HTTPException(400, f"Error: {str(e)}")

    result = await db.execute(select(VideoEmbedding).where(VideoEmbedding.video_id == video_id).limit(1))
    if not result.scalars().first():
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_text(full_text)
        curr_words = 0
        for chunk in chunks:
            vector = embeddings.embed_query(chunk)
            est_time = int(curr_words / 2.5)
            db.add(VideoEmbedding(video_id=video_id, content=chunk, embedding=vector, start_time=est_time))
            curr_words += len(chunk.split())
        await db.commit()
    
    resources = await generate_resources_on_load(full_text)
    return {"status": "success", "message": "Processed!", "recommendations": resources}

if os.path.exists("ui/dist"):
    app.mount("/assets", StaticFiles(directory="ui/dist/assets"), name="assets")
    @app.get("/")
    async def read_index(): return FileResponse("ui/dist/index.html")