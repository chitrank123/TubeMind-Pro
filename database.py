import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy import text 
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from dotenv import load_dotenv
load_dotenv()
# Update with your credentials if needed
DATABASE_URL = os.getenv("DATABASE_URL")

Base = declarative_base()

# --- 1. AUTH MODELS ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    sessions = relationship("Session", back_populates="user")

# --- 2. HISTORY MODELS ---
class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_id = Column(String) 
    title = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    role = Column(String) 
    content = Column(Text)
    metadata_ = Column("metadata", JSON, nullable=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("Session", back_populates="messages")

# --- 3. RAG MODEL ---
class VideoEmbedding(Base):
    __tablename__ = "video_embeddings"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String, index=True)
    content = Column(Text)
    embedding = Column(Vector(384))
    start_time = Column(Integer)

# --- ENGINE CONFIGURATION (THE FIX) ---
engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    pool_pre_ping=True, # <--- Checks connection liveness before use
    pool_size=10,       # <--- Keeps 10 connections ready
    max_overflow=20,    # <--- Allows spikes up to 20
    pool_recycle=1800   # <--- Refreshes connections every 30 mins
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session