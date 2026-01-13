import os
import json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from groq import Groq
from ddgs import DDGS
import wikipedia

# --- STATE DEFINITION ---
class AgentState(TypedDict):
    query: str
    context: str        
    chat_history: List[Dict[str, str]]
    next_step: str      
    final_answer: str
    reasoning: str
    suggestions: List[str]
    metadata: Dict[str, Any] 

# --- NODES ---

def orchestrator_node(state: AgentState):
    """
    ROUTER: Bias towards RAG for Compound Queries.
    """
    client = Groq()
    
    history = state.get('chat_history', [])
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history[-3:]])
    
    # NEW LOGIC: If query is mixed ("Summarize video AND search web"), force RAG.
    # The RAG agent is now smart enough to handle the search part.
    prompt = f"""
    You are the Router. Analyze the user's intent.
    
    Context:
    - History: {history_text}
    - Query: {state['query']}
    
    Routing Rules:
    1. 'RAG': (DEFAULT) IF the user mentions "this video", "summary", "transcript", OR asks a mixed question like "Summarize video and find links".
    2. 'SEARCH': ONLY if the user asks purely about "latest news", "current events", or topics NOT related to the video content.
    3. 'CHAT': Greetings/Small talk.
    
    Return JSON: {{ "thought": "Reasoning...", "decision": "RAG/SEARCH/CHAT" }}
    """
    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile", response_format={"type": "json_object"}
        )
        data = json.loads(resp.choices[0].message.content)
        decision = data.get("decision", "RAG").strip().upper()
        thought = data.get("thought", "Analyzing intent...")
    except:
        decision = "RAG"
        thought = "Error in routing, defaulting to RAG."
        
    if "SEARCH" in decision: decision = "SEARCH"
    elif "CHAT" in decision: decision = "CHAT"
    else: decision = "RAG"
    
    return {"next_step": decision, "reasoning": f"Orchestrator: {thought}"}

def rag_agent_node(state: AgentState):
    """
    HYBRID RAG AGENT:
    1. Generates Video Answer.
    2. (Optional) Performs Web Search if requested in the same query.
    3. Judges the final result.
    """
    client = Groq()
    query = state['query']
    context = state['context']
    history = state.get('chat_history', [])
    history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history[-5:]])

    # --- STEP 1: CHECK FOR "EXTERNAL SOURCE" INTENT ---
    # Does the user want outside info too?
    search_results = ""
    keywords_to_trigger_search = ["other sources", "external links", "more info", "search web", "find articles"]
    
    if any(k in query.lower() for k in keywords_to_trigger_search):
        try:
            # Quick extraction of main topic to search
            topic_prompt = f"Extract main topic from query for web search: {query}"
            topic_resp = client.chat.completions.create(messages=[{"role": "user", "content": topic_prompt}], model="llama-3.3-70b-versatile")
            search_topic = topic_resp.choices[0].message.content.strip()
            
            # Perform Search
            with DDGS() as ddgs:
                results = ddgs.text(f"{search_topic} tutorial guide", max_results=2)
                for r in results:
                    search_results += f"- [{r['title']}]({r['href']})\n"
        except:
            search_results = ""

    # --- STEP 2: GENERATE HYBRID ANSWER ---
    # We feed both Video Context AND Search Results (if any) to the Writer
    system_prompt = f"""
    You are an expert tutor. Answer based on the Video Context.
    
    VIDEO CONTEXT:
    {context}
    
    EXTERNAL WEB RESULTS (If requested):
    {search_results}
    
    INSTRUCTIONS:
    1. Primary: Summarize/Answer using the Video Context. Cite timestamps {{MM:SS}}.
    2. Secondary: If 'EXTERNAL WEB RESULTS' are present, append them at the end under a "📚 External Resources" section.
    3. If the answer is not in the video, say so.
    """
    
    draft_resp = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        model="llama-3.3-70b-versatile"
    )
    draft = draft_resp.choices[0].message.content
    
    # --- STEP 3: JUDGE ---
    judge_prompt = f"""
    Quality Control.
    Query: {query}
    Answer: {draft}
    
    Return JSON: {{ "thought": "Evaluation...", "score": 85 }}
    """
    try:
        j_resp = client.chat.completions.create(
            messages=[{"role": "user", "content": judge_prompt}],
            model="llama-3.3-70b-versatile", response_format={"type": "json_object"}
        )
        data = json.loads(j_resp.choices[0].message.content)
        score = data.get("score", 0)
        thought = data.get("thought", f"Quality check passed with score {score}.")
    except:
        score, thought = 0, "Evaluation error."

    # If we did a search, mention it in the reasoning
    final_reasoning = f"Judge: {thought}"
    if search_results:
        final_reasoning = f"Hybrid Agent: Fetched external sources & {final_reasoning}"

    return {
        "final_answer": draft, 
        "reasoning": final_reasoning,
        "metadata": {"score": score, "reason": "Hybrid RAG Execution"} 
    }

def search_agent_node(state: AgentState):
    """Fallback Search Agent (Only for purely non-video queries)"""
    client = Groq()
    query = state['query']
    
    # Deep Thought Plan
    plan_prompt = f"User Query: {query}. Plan search keywords."
    try:
        plan_resp = client.chat.completions.create(messages=[{"role": "user", "content": plan_prompt}], model="llama-3.3-70b-versatile")
        search_thought = plan_resp.choices[0].message.content
    except: search_thought = "Planning search..."
    
    results_text = ""
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3): results_text += f"{r['title']}: {r['body']}\n"
    except: pass
    
    if not results_text:
        try:
            page = wikipedia.summary(query, sentences=3)
            results_text += f"Source: Wikipedia\nSnippet: {page}"
        except: results_text = "No sources found."
        
    prompt = f"Answer using results. Format links [Title](URL).\n\nQ: {query}\n\nInfo:\n{results_text}"
    resp = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile")
    
    return {
        "final_answer": resp.choices[0].message.content, 
        "reasoning": f"Searcher: {search_thought}",
        "metadata": {"score": 100, "reason": "External Web Source"}
    }

def chat_agent_node(state: AgentState):
    """CHIT CHAT"""
    client = Groq()
    resp = client.chat.completions.create(messages=[{"role": "user", "content": state['query']}], model="llama-3.3-70b-versatile")
    return {
        "final_answer": resp.choices[0].message.content, 
        "reasoning": "Conversational Agent: Generating friendly response...",
        "metadata": {"score": 100, "reason": "General Conversation"}
    }

def suggestion_node(state: AgentState):
    client = Groq()
    prompt = f"""
    Based on this answer, suggest 3 short follow-up questions.
    Return JSON: {{ "questions": ["Q1", "Q2", "Q3"] }}
    Answer: {state['final_answer'][:1000]}
    """
    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}], 
            model="llama-3.3-70b-versatile", response_format={"type": "json_object"}
        )
        data = json.loads(resp.choices[0].message.content)
        suggestions = data.get("questions", [])
    except:
        suggestions = []
        
    return {"suggestions": suggestions}

# --- GRAPH CONSTRUCTION ---
workflow = StateGraph(AgentState)
workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("search_agent", search_agent_node)
workflow.add_node("chat_agent", chat_agent_node)
workflow.add_node("suggestion_engine", suggestion_node)

workflow.set_entry_point("orchestrator")

def router(state):
    if state['next_step'] == "RAG": return "rag_agent"
    elif state['next_step'] == "SEARCH": return "search_agent"
    else: return "chat_agent"

workflow.add_conditional_edges("orchestrator", router, {"rag_agent": "rag_agent", "search_agent": "search_agent", "chat_agent": "chat_agent"})
workflow.add_edge("rag_agent", "suggestion_engine")
workflow.add_edge("search_agent", "suggestion_engine")
workflow.add_edge("chat_agent", "suggestion_engine")
workflow.add_edge("suggestion_engine", END)

app_graph = workflow.compile()