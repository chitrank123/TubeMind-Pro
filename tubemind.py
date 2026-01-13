import os
# We use LangChain's loader instead of the raw library
from langchain_community.document_loaders import YoutubeLoader 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from groq import Groq
from dotenv import load_dotenv
load_dotenv()
# --- CONFIGURATION ---
# PASTE YOUR KEY HERE
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

# --- PART 1: THE ETL PIPELINE ---

def extract_transcript(video_url):
    """
    EXTRACT: Uses LangChain to fetch the real video transcript.
    """
    print(f"--- Fetching transcript for: {video_url} ---")
    try:
        # LangChain handles the API calls for us
        loader = YoutubeLoader.from_youtube_url(
            video_url, 
            add_video_info=False
        )
        docs = loader.load()
        # The loader returns a list of "Documents", we just need the text content
        full_text = " ".join([doc.page_content for doc in docs])
        return full_text
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None

def create_vector_db(text):
    """
    TRANSFORM & LOAD: Chunk text -> Embed -> Store in DB
    """
    print("1. Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_text(text)
    
    print("2. Creating Embeddings (Converting text to numbers)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    print("3. Saving to ChromaDB (Vector Store)...")
    # We use a new collection name to avoid conflicts
    db = Chroma.from_texts(
        texts=chunks, 
        embedding=embeddings, 
        collection_name="tubemind_real",
        persist_directory="./chroma_db_real"
    )
    return db

# --- PART 2: THE RAG SYSTEM ---

def query_llm(query, db):
    """
    RETRIEVAL & GENERATION: Search DB -> Send to AI
    """
    # 1. Retrieval
    docs = db.similarity_search(query, k=3)
    context_text = "\n\n".join([doc.page_content for doc in docs])
    
    # 2. Prompt Engineering
    system_prompt = f"""
    You are a helpful assistant. Answer the user's question based ONLY on the context provided below.
    If the answer is not in the context, say "I don't know based on this video."
    
    Context:
    {context_text}
    """
    
    # 3. Generation (Groq)
    client = Groq()
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        model="llama-3.3-70b-versatile",
    )
    
    return chat_completion.choices[0].message.content

# --- MAIN APP LOOP ---

if __name__ == "__main__":
    print("--- TubeMind: Chat with YouTube (REAL VERSION) ---")
    url = input("Enter YouTube URL: ")
    
    # Run ETL
    raw_text = extract_transcript(url)
    
    if raw_text:
        vector_db = create_vector_db(raw_text)
        print("\nVideo processed! Ask questions (type 'exit' to quit).")
        
        while True:
            user_q = input("\nQ: ")
            if user_q.lower() == "exit":
                break
            
            try:
                answer = query_llm(user_q, vector_db)
                print(f"AI: {answer}")
            except Exception as e:
                print(f"Error: {e}")
    else:
        print("Failed to get text. Try a different video (make sure it has captions).")