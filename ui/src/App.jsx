import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
// --- ICONS (Simple SVGs to avoid extra dependencies) ---
const MenuIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>
const XIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 18 18"/></svg>
const VideoIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 8-6 4 6 4V8Z"/><rect width="14" height="12" x="2" y="6" rx="2" ry="2"/></svg>
const ChatIcon = () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg>

const getVideoId = (url) => {
  if (!url) return null
  const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/
  const match = url.match(regExp)
  return (match && match[2].length === 11) ? match[2] : null
}
const parseTime = (timeStr) => {
  const [min, sec] = timeStr.split(':').map(Number)
  return min * 60 + sec
}

export default function App() {
  // --- AUTH STATE ---
  const [user, setUser] = useState(null)
  const [authMode, setAuthMode] = useState('login')
  const [authInput, setAuthInput] = useState({ username: '', password: '' })
  
  // --- APP STATE ---
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [url, setUrl] = useState('')
  const [videoId, setVideoId] = useState(null)
  const [seekTime, setSeekTime] = useState(0)

  // Thoughts Streaming State
  const [streamingThoughts, setStreamingThoughts] = useState([])
  const [isThinking, setIsThinking] = useState(false)

  // Resources
  const [recs, setRecs] = useState({ topic: '', videos: [], blogs: [] })
  const [activeTab, setActiveTab] = useState('resources') 

  // --- MOBILE STATE ---
  const [isLeftOpen, setIsLeftOpen] = useState(false) // Sessions Menu
  const [isRightOpen, setIsRightOpen] = useState(false) // Tools/Video Panel

  const ws = useRef(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamingThoughts])

  // 1. AUTH ACTIONS
  const handleAuth = async () => {
    // NOTE: Using IP provided in previous context
    const endpoint = authMode === 'login' ? '/auth/login' : '/auth/register'
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(authInput)
    })
    const data = await res.json()
    if(!res.ok) return alert(data.detail)
    
    if (authMode === 'login') {
      setUser({ username: data.username, token: data.access_token })
      loadSessions(data.username)
    } else {
      alert("Account created! Please login.")
      setAuthMode('login')
    }
  }

  // 2. SESSION ACTIONS
  const loadSessions = async (username) => {
    const res = await fetch(`${API_BASE}/api/sessions/${username}`)
    const data = await res.json()
    setSessions(data)
  }

  const createSession = async () => {
    if (!url || !user) return
    const id = getVideoId(url)
    if (!id) return alert("Invalid URL")

    setIsThinking(true)
    const processRes = await fetch('${API_BASE}/api/process', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    })
    const pData = await processRes.json()
    setIsThinking(false)
    setRecs(pData.recommendations)

    const res = await fetch('${API_BASE}/api/session/create', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: id, title: pData.recommendations.topic || "New Chat", username: user.username })
    })
    const sData = await res.json()
    
    setVideoId(id)
    setCurrentSessionId(sData.session_id)
    setSessions(prev => [{ id: sData.session_id, title: pData.recommendations.topic, video_id: id }, ...prev])
    setMessages([{ role: 'ai', text: `Session Ready! Topic: ${pData.recommendations.topic}` }])
    
    // On mobile, auto-close tools and show chat after creating
    setIsRightOpen(false) 
    
    connectWebSocket(sData.session_id, user.token)
  }

  const selectSession = async (session) => {
    setCurrentSessionId(session.id)
    setVideoId(session.video_id)
    const videoUrl = `https://www.youtube.com/watch?v=${session.video_id}`
    setUrl(videoUrl)
    
    const historyRes = await fetch(`${API_BASE}/api/history/${session.id}`)
    const historyData = await historyRes.json()
    setMessages(historyData)
    
    try {
      const res = await fetch('${API_BASE}/api/process', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: videoUrl })
      })
      const data = await res.json()
      setRecs(data.recommendations)
    } catch (e) { console.error(e) }
    
    connectWebSocket(session.id, user.token)
    
    // Mobile UX: Close menu after selection
    setIsLeftOpen(false)
  }

  // 3. WEBSOCKET
  const connectWebSocket = (sessId, token) => {
    if (ws.current) ws.current.close()
    ws.current = new WebSocket(`ws://210.89.34.6:8001/ws/chat?token=${token}&session_id=${sessId}`)
    
    ws.current.onmessage = (event) => {
      const response = JSON.parse(event.data)
      if (response.type === 'thought') {
        setIsThinking(true)
        setStreamingThoughts(prev => [...prev, response.data])
      } else if (response.type === 'result') {
        setIsThinking(false)
        setStreamingThoughts([]) 
        setMessages(prev => [...prev, { 
          role: 'ai', 
          text: response.data, 
          meta: response.meta, 
          suggestions: response.suggestions
        }])
      }
    }
  }

  const sendMessage = (msgText = input) => {
    if (!msgText || !ws.current) return
    setMessages(prev => [...prev, { role: 'user', text: msgText }])
    setInput('')
    ws.current.send(JSON.stringify({ message: msgText, url: url }))
  }

  const ThinkingAccordion = ({ thoughts }) => {
    const [isOpen, setIsOpen] = useState(false);
    if (!thoughts || thoughts.length === 0) return null;
    return (
      <div className="mb-3 border border-slate-700/50 rounded-lg overflow-hidden bg-slate-900/50">
        <button onClick={() => setIsOpen(!isOpen)} className="w-full flex items-center justify-between px-3 py-2 text-xs font-mono text-cyan-400 bg-slate-800/50 hover:bg-slate-800 transition-colors">
          <div className="flex items-center gap-2"><span className="animate-pulse">🧠</span> {isOpen ? "Hide Thinking" : "View Thinking"}</div>
          <span>{isOpen ? "▲" : "▼"}</span>
        </button>
        {isOpen && (
          <div className="p-3 bg-black/20 space-y-1">
            {thoughts.map((thought, idx) => (
              <div key={idx} className="text-xs text-slate-400 font-mono border-l-2 border-slate-700 pl-2">{thought}</div>
            ))}
          </div>
        )}
      </div>
    );
  }

  const renderMarkdown = (text) => {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          a: ({node, ...props}) => <a {...props} className="text-cyan-400 underline hover:text-cyan-300" target="_blank" rel="noopener noreferrer" />
      }}>
        {text}
      </ReactMarkdown>
    )
  }

  if (!user) {
    return (
      <div className="h-screen w-screen bg-slate-950 flex items-center justify-center text-white font-sans p-4">
        <div className="bg-slate-900 p-8 rounded-2xl border border-slate-800 w-full max-w-md shadow-2xl">
          <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent mb-6 text-center">TubeMind Pro</h1>
          <div className="space-y-4">
            <input className="w-full p-3 bg-slate-800 rounded border border-slate-700 outline-none focus:border-cyan-500" 
              placeholder="Username" value={authInput.username} onChange={e => setAuthInput({...authInput, username: e.target.value})} />
            <input type="password" class="w-full p-3 bg-slate-800 rounded border border-slate-700 outline-none focus:border-cyan-500" 
              placeholder="Password" value={authInput.password} onChange={e => setAuthInput({...authInput, password: e.target.value})} />
            <button onClick={handleAuth} className="w-full bg-cyan-600 hover:bg-cyan-500 p-3 rounded font-bold transition-all">
              {authMode === 'login' ? 'Login' : 'Create Account'}
            </button>
            <p className="text-center text-slate-500 text-sm cursor-pointer hover:text-white" onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}>
              {authMode === 'login' ? 'Need an account? Register' : 'Have an account? Login'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // --- MOBILE SIDEBAR BACKDROP ---
  const Backdrop = ({ onClick }) => (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden animate-in fade-in" onClick={onClick} />
  )

  return (
    <div className="h-screen w-screen bg-slate-950 text-white flex flex-col md:flex-row overflow-hidden font-sans relative">
      
      {/* --- MOBILE HEADER --- */}
      <div className="md:hidden h-14 border-b border-slate-800 bg-slate-900 flex items-center justify-between px-4 z-30 shrink-0">
         <button onClick={() => setIsLeftOpen(true)} className="text-slate-300 hover:text-white"><MenuIcon /></button>
         <span className="font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">TubeMind</span>
         <button onClick={() => setIsRightOpen(true)} className="text-slate-300 hover:text-white"><VideoIcon /></button>
      </div>

      {/* --- LEFT SIDEBAR (SESSIONS) --- */}
      {/* Mobile Backdrop */}
      {isLeftOpen && <Backdrop onClick={() => setIsLeftOpen(false)} />}
      
      <div className={`
        fixed md:relative inset-y-0 left-0 z-50 w-64 bg-black border-r border-slate-800 flex flex-col transition-transform duration-300 ease-in-out
        ${isLeftOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}>
        <div className="p-4 border-b border-slate-800 flex justify-between items-center">
           <div>
             <div className="font-bold text-lg mb-1">{user.username}</div>
             <div className="text-xs text-slate-500">Pro Plan</div>
           </div>
           {/* Close Button Mobile Only */}
           <button onClick={() => setIsLeftOpen(false)} className="md:hidden text-slate-500"><XIcon/></button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map(sess => (
            <div key={sess.id} onClick={() => selectSession(sess)} 
              className={`p-3 rounded cursor-pointer text-sm truncate ${currentSessionId === sess.id ? 'bg-slate-800 text-cyan-400' : 'text-slate-400 hover:bg-slate-900'}`}>
              {sess.title || "Untitled Chat"}
            </div>
          ))}
        </div>
        <div className="p-4 border-t border-slate-800">
           <button onClick={() => {setUser(null); setMessages([]); setSessions([]);}} className="text-red-400 text-sm hover:underline">Logout</button>
        </div>
      </div>
      
      {/* --- CENTER: CHAT AREA --- */}
      <div className="flex-1 flex flex-col h-full min-w-0 relative">
        {/* Desktop Header (Hidden on Mobile) */}
        <div className="hidden md:flex p-4 border-b border-slate-800 bg-slate-900/90 backdrop-blur z-10 justify-between items-center">
          <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">TubeMind Pro</h1>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6 scroll-smooth">
          {messages.length === 0 && <div className="text-center text-slate-600 mt-20 px-4">Tap the Video Icon to load a YouTube URL!</div>}
          
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`max-w-[95%] md:max-w-[85%] p-4 rounded-2xl shadow-lg ${msg.role === 'user' ? 'bg-blue-600' : 'bg-slate-800 border border-slate-700'}`}>
                {msg.role === 'ai' && msg.meta && msg.meta.thoughts && (
                  <ThinkingAccordion thoughts={msg.meta.thoughts} />
                )}
                {msg.meta && msg.meta.score > 0 && (
                  <div className={`mb-2 text-xs font-mono border-b border-slate-700 pb-2 flex justify-between ${msg.meta.score < 70 ? 'text-red-400' : 'text-green-400'}`}>
                    <span>🏆 Score: {msg.meta.score}%</span>
                  </div>
                )}
                <div className="leading-relaxed whitespace-pre-wrap text-sm">
                  {renderMarkdown(msg.text)}
                </div>
              </div>
              {msg.suggestions && msg.suggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2 animate-in fade-in slide-in-from-top-2 duration-500">
                  {msg.suggestions.map((sugg, sIdx) => (
                    <button key={sIdx} onClick={() => sendMessage(sugg)}
                      className="text-xs bg-slate-900 border border-cyan-900/50 text-cyan-200 px-3 py-1.5 rounded-full hover:bg-cyan-900/30 hover:border-cyan-500 transition-all cursor-pointer">
                      ✨ {sugg}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}

          {isThinking && (
             <div className="flex flex-col items-start animate-pulse">
                <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700 w-64">
                   <div className="text-xs text-cyan-400 font-mono mb-2">🧠 Thinking Process...</div>
                   {streamingThoughts.map((t, i) => (
                      <div key={i} className="text-xs text-slate-500 font-mono truncate">{t}</div>
                   ))}
                </div>
             </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 border-t border-slate-800 bg-slate-900 z-10 shrink-0">
          <div className="flex gap-2 max-w-4xl mx-auto">
            <input className="flex-1 p-3.5 rounded-xl bg-slate-800 border border-slate-700 focus:border-cyan-500 outline-none text-sm md:text-base"
              placeholder="Ask a question..." value={input} onChange={e => setInput(e.target.value)}
              onKeyPress={e => e.key === 'Enter' && sendMessage()} 
              disabled={!currentSessionId || isThinking}
            />
            <button onClick={() => sendMessage()} disabled={!currentSessionId} className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 md:px-6 rounded-xl font-bold disabled:opacity-50">
               <span className="hidden md:inline">Send</span>
               <span className="md:hidden">➤</span>
            </button>
          </div>
        </div>
      </div>

      {/* --- RIGHT SIDEBAR (TOOLS) --- */}
      {/* Mobile Backdrop */}
      {isRightOpen && <Backdrop onClick={() => setIsRightOpen(false)} />}
      
      <div className={`
        fixed md:relative inset-y-0 right-0 z-50 w-full md:w-[480px] bg-black border-l border-slate-800 flex flex-col transition-transform duration-300 ease-in-out
        ${isRightOpen ? 'translate-x-0' : 'translate-x-full md:translate-x-0'}
      `}>
        
        {/* Mobile Header for Right Panel */}
        <div className="md:hidden p-3 bg-slate-900 border-b border-slate-800 flex justify-between items-center">
            <span className="font-bold text-slate-200">Video & Tools</span>
            <button onClick={() => setIsRightOpen(false)} className="text-slate-400"><XIcon/></button>
        </div>

        <div className="h-[250px] md:h-[250px] shrink-0 bg-black relative border-b border-slate-800">
           {videoId ? (
             <iframe src={`https://www.youtube.com/embed/${videoId}?start=${seekTime}&autoplay=1`} 
               className="absolute inset-0 w-full h-full" allow="autoplay; encrypted-media" allowFullScreen></iframe>
           ) : <div className="h-full flex flex-col items-center justify-center text-slate-700"><span className="text-4xl">▶️</span></div>}
        </div>

        <div className="p-3 bg-slate-900 flex gap-2 border-b border-slate-800 shrink-0">
           <input className="flex-1 bg-slate-800 border border-slate-700 px-3 py-2 rounded-lg text-sm outline-none text-slate-200" 
                  placeholder="Paste YouTube URL..." value={url} onChange={e=>setUrl(e.target.value)}/>
           <button onClick={createSession} className="bg-slate-200 hover:bg-white text-black px-3 rounded-lg text-sm font-bold">New</button>
        </div>

        <div className="flex border-b border-slate-800 bg-slate-950">
           <button onClick={() => setActiveTab('resources')} className={`flex-1 p-3 text-sm font-bold ${activeTab === 'resources' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-slate-500'}`}>📚 Resources</button>
        </div>

        <div className="flex-1 overflow-y-auto bg-slate-950 p-4 relative">
          {activeTab === 'resources' && (
             <div className="space-y-6">
                {!recs.topic && <p className="text-center text-slate-600 mt-10">Load a video to start a session.</p>}
                {recs.videos.length > 0 && (
                  <div>
                    <h3 className="font-bold text-red-400 mb-2 uppercase text-xs">Related Videos</h3>
                    {recs.videos.map((v, i) => <a key={i} href={v.link} target="_blank" className="block p-3 mb-2 bg-slate-900 border border-slate-800 rounded hover:border-red-500 text-sm">{v.title}</a>)}
                  </div>
                )}
                {recs.blogs.length > 0 && (
                  <div>
                    <h3 className="font-bold text-green-400 mb-2 uppercase text-xs">Related Articles</h3>
                    {recs.blogs.map((b, i) => <a key={i} href={b.link} target="_blank" className="block p-3 mb-2 bg-slate-900 border border-slate-800 rounded hover:border-green-500 text-sm">{b.title}</a>)}
                  </div>
                )}
             </div>
          )}
        </div>
      </div>
    </div>
  )
}