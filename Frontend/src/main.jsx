import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bot, Send, Sparkles, Plus, PanelLeftClose, PanelLeftOpen, Settings2, Zap, ShieldCheck, Clock3, Hash, ChevronDown, MessageSquare, Activity, Copy, Check, AlertCircle } from 'lucide-react';
import './styles.css';

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const makeId = () => `s-${crypto.randomUUID().slice(0, 8)}`;
const starters = [
  { icon: '✦', title: 'Explain a complex topic', prompt: 'Explain how large language models work in simple terms.' },
  { icon: '⌘', title: 'Help me write code', prompt: 'Write a Python function that checks whether a string is a palindrome.' },
  { icon: '↗', title: 'Brainstorm ideas', prompt: 'Give me five creative ideas for a productivity app.' },
];

function App() {
  const [sessionId, setSessionId] = useState(makeId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [health, setHealth] = useState(null);
  const [copied, setCopied] = useState(-1);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { fetch(`${API}/health`).then(r => r.json()).then(setHealth).catch(() => setHealth({status:'offline'})); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  const newChat = () => { setSessionId(makeId()); setMessages([]); setError(''); setInput(''); inputRef.current?.focus(); };
  const send = async (text = input) => {
    const clean = text.trim();
    if (!clean || loading) return;
    setInput(''); setError(''); setMessages(prev => [...prev, { role: 'user', content: clean }]); setLoading(true);
    try {
      const response = await fetch(`${API}/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: clean, ...(systemPrompt.trim() ? { system_prompt: systemPrompt.trim() } : {}) })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Something went wrong. Please try again.');
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply, metadata: data.metadata }]);
    } catch (e) {
      const message = e.message === 'Failed to fetch' ? 'Could not connect to Lyftr AI. Check that the backend is running and VITE_API_URL is configured.' : e.message;
      setError(message); setMessages(prev => [...prev, { role: 'error', content: message }]);
    } finally { setLoading(false); }
  };
  const onKeyDown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
  const copyText = async (text, index) => { await navigator.clipboard.writeText(text); setCopied(index); setTimeout(() => setCopied(-1), 1300); };

  return <div className="app-shell">
    <aside className={`sidebar ${sidebar ? '' : 'collapsed'}`}>
      <div className="brand-row"><div className="brand-mark"><Sparkles size={18}/></div>{sidebar && <span className="brand-name">lyftr<span>.</span></span>}<button className="icon-btn collapse-btn" onClick={() => setSidebar(!sidebar)} aria-label="Toggle sidebar">{sidebar ? <PanelLeftClose size={18}/> : <PanelLeftOpen size={18}/>}</button></div>
      {sidebar && <><button className="new-chat" onClick={newChat}><Plus size={17}/> New chat <span>⌘ K</span></button><div className="side-label">WORKSPACE</div><div className="nav-item active"><MessageSquare size={16}/> <span>AI Assistant</span></div><div className="nav-item"><Activity size={16}/> <span>System status</span><i className={health?.status === 'ok' ? 'online-dot' : 'offline-dot'}/></div><div className="sidebar-bottom"><div className="plan-card"><div className="plan-icon"><Zap size={15}/></div><div><b>Built for reliability</b><small>Smart routing · Cached answers</small></div></div><div className="profile"><div className="avatar">L</div><div><b>Lyftr Workspace</b><small>Personal plan</small></div><ChevronDown size={15}/></div></div></>}
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="crumb"><span>Workspace</span><span className="slash">/</span><b>AI Assistant</b><span className="beta">BETA</span></div><div className="top-actions"><div className={`status-pill ${health?.status === 'ok' ? 'good' : 'bad'}`}><span/>{health?.status === 'ok' ? 'Systems operational' : 'Backend unavailable'}</div><button className={`icon-btn ${showSettings ? 'selected' : ''}`} onClick={() => setShowSettings(!showSettings)} title="Session settings"><Settings2 size={18}/></button></div></header>
      {showSettings && <div className="settings-pop"><div className="settings-title">Session settings</div><label htmlFor="system-prompt-input">System prompt <span>OPTIONAL</span></label><textarea id="system-prompt-input" data-testid="system-prompt-input" value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} placeholder="Give Lyftr AI a role or set response preferences..."/><small>Applies to messages sent in this session.</small></div>}
      <section className="chat-area">
        {messages.length === 0 ? <div className="welcome-wrap"><div className="welcome-icon"><Sparkles size={24}/></div><div className="eyebrow">YOUR AI WORKSPACE</div><h1>Ideas into action.<br/><span>Let's get there.</span></h1><p className="welcome-copy">Meet Lyftr AI — your thoughtful, reliable AI assistant.<br/>Ask anything and let's make something happen.</p><div className="starter-grid">{starters.map((s,i)=><button className="starter-card" key={i} onClick={() => send(s.prompt)}><span className="starter-symbol">{s.icon}</span><b>{s.title}</b><small>{s.prompt}</small></button>)}</div></div> : <div className="message-list">{messages.map((m,i) => <div className={`message-row ${m.role}`} key={i}>{m.role === 'assistant' ? <div className="message-avatar"><Sparkles size={15}/></div> : m.role === 'error' ? <div className="message-avatar error-avatar"><AlertCircle size={15}/></div> : <div className="user-avatar">Y</div>}<div className="message-content">{m.role === 'assistant' && <div className="message-author">Lyftr AI <span>·</span> <span className="assistant-tag">ASSISTANT</span></div>}<div className="message-text">{m.content}</div>{m.metadata && <div className="metadata-card"><div className="meta-head"><span className={`source-dot ${m.metadata.resolution_source === 'LLM_CACHE' ? 'cached' : ''}`}/><b data-testid="meta-source">{m.metadata.resolution_source}</b><span className="meta-divider"/><span className="model-name" data-testid="meta-model">{m.metadata.model}</span><button className="copy-btn" onClick={() => copyText(m.content,i)}>{copied === i ? <Check size={13}/> : <Copy size={13}/>}</button></div><div className="meta-stats"><span><Clock3 size={13}/><b data-testid="meta-latency">{m.metadata.latency_ms} ms</b></span><span><Hash size={13}/> In <b data-testid="meta-input-tokens">{m.metadata.input_tokens}</b></span><span><Hash size={13}/> Out <b data-testid="meta-output-tokens">{m.metadata.output_tokens}</b></span>{m.metadata.key_id && <span className="key-label"><ShieldCheck size={13}/>{m.metadata.key_id}</span>}</div></div>}</div></div>)}{loading && <div className="message-row assistant"><div className="message-avatar"><Sparkles size={15}/></div><div className="typing"><i/><i/><i/><span>Lyftr is thinking</span></div></div>}<div ref={bottomRef}/></div>}
      </section>
      <div className="composer-wrap"><div className="composer"><textarea ref={inputRef} data-testid="chat-input" value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKeyDown} placeholder="Message Lyftr AI..." rows={1} disabled={loading}/><div className="composer-footer"><span><span className="composer-spark">✦</span> Thoughtful answers, powered by AI</span><button data-testid="send-button" className="send-btn" onClick={() => send()} disabled={!input.trim() || loading} aria-label="Send message"><Send size={16}/></button></div></div><div className="disclaimer">Lyftr AI can make mistakes. Verify important information.</div></div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
