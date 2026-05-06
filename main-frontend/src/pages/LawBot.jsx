import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Trash2, ChevronDown, ChevronUp, Scale, Mic, Languages, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = '/api/bot/lawbot';

export default function LawBot({ token }) {
  const navigate = useNavigate();

  // ── Persistence Logic ──────────────────────────────────────────
  const storageKey = `lawbot_state_${token.slice(-10)}`;
  
  const getSavedState = () => {
    try {
      const saved = localStorage.getItem(storageKey);
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  };

  const saved = getSavedState();

  const [messages, setMessages] = useState(saved.messages || []);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Sync to localStorage
  useEffect(() => {
    const stateToSave = { messages };
    localStorage.setItem(storageKey, JSON.stringify(stateToSave));
  }, [messages]);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const addMsg = (role, content, extra = {}) => {
    setMessages(prev => [...prev, { role, content, time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), ...extra }]);
  };

  const [isListening, setIsListening] = useState(false);
  const [isTransliterating, setIsTransliterating] = useState(false);

  const isUrdu = (text) => /[\u0600-\u06FF]/.test(text);

  const transliterate = async (text) => {
    try {
      const res = await fetch('/api/bot/romanize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const d = await res.json();
      return d.romanized || text;
    } catch { return text; }
  };

  const startSpeech = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return alert("Speech recognition not supported in this browser.");
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      setInput(transcript);
    };
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  const handleSend = async (overrideText) => {
    let text = typeof overrideText === 'string' ? overrideText.trim() : input.trim();
    if (!text || loading) return;

    if (isUrdu(text)) {
      setIsTransliterating(true);
      text = await transliterate(text);
      setIsTransliterating(false);
    }

    setInput('');
    addMsg('user', text);
    setLoading(true);

    try {
      const history = messages.filter(m => !m.isError).map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content
      })).slice(-4);

      const res = await fetch(`${API}/chat`, {
        method: 'POST', headers,
        body: JSON.stringify({ query: text, history })
      });
      const data = await res.json();

      if (data.error) {
        addMsg('bot', data.error, { isError: true });
      } else {
        addMsg('bot', data.response || 'No response received.', {
          sources: data.sources || []
        });
      }
    } catch (err) {
      addMsg('bot', `Error: ${err.message}`, { isError: true });
    }
    setLoading(false);
  };

  const clearChat = () => {
    setMessages([]);
    localStorage.removeItem(storageKey);
  };

  // ── Sources Expandable ─────────────────────────────────────────
  function SourcesBlock({ sources }) {
    const [open, setOpen] = useState(false);
    if (!sources || sources.length === 0) return null;
    return (
      <div>
        <div className="sources-toggle" onClick={() => setOpen(!open)}>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {open ? 'Hide' : 'View'} Cited Sources ({sources.length})
        </div>
        {open && sources.map((s, i) => (
          <div key={i} className="source-item">
            <strong>📄 {s.source}</strong>
            {s.preview?.slice(0, 300)}...
          </div>
        ))}
      </div>
    );
  }

  return (
    <motion.div className="bot-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="bot-topbar">
        <div className="bot-topbar-left">
          <button className="btn btn-outline" onClick={() => navigate('/dashboard')} style={{ padding: '0.4rem 0.8rem', borderRadius: 8 }}>
            <ArrowLeft size={16} /> Back
          </button>
          <div className="bot-status-dot" style={{ background: '#d946ef', boxShadow: '0 0 10px #d946ef' }} />
          <span style={{ fontWeight: 600, fontSize: '1.05rem' }}>⚖️ Lawyer Bot Workspace</span>
        </div>
      </div>

      <div className="bot-body">
        <div className="bot-main">
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-welcome">
                <div className="chat-welcome-icon">⚖️</div>
                <h3>Pakistan Legal Guidance Assistant</h3>
                <p>General legal guidance based on uploaded Law Books. Not a substitute for a lawyer.</p>

                <div style={{ marginTop: '1rem', fontSize: '0.82rem', color: 'var(--text-muted)', fontStyle: 'italic', background: 'var(--bg-surface)', padding: '0.6rem 1rem', borderRadius: 8, borderLeft: '2px solid var(--accent)' }}>
                  Try: "What is Section 144?" or "What are tenant rights under Pakistan law?"
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`msg-row ${msg.role === 'user' ? 'user-row' : ''}`}>
                <div className={`msg-avatar ${msg.role === 'user' ? 'user-avatar-sm' : 'bot-avatar'}`}>
                  {msg.role === 'user' ? 'You' : '⚖️'}
                </div>
                <div>
                  <div className={`msg-bubble ${msg.role === 'user' ? 'user-bubble' : msg.isError ? 'error-bubble' : 'bot-bubble'}`}>
                    <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>
                    {msg.sources && <SourcesBlock sources={msg.sources} />}
                  </div>
                  <div className="msg-time">{msg.time}</div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="msg-row">
                <div className="msg-avatar bot-avatar">⚖️</div>
                <div className="msg-bubble bot-bubble" style={{ display: 'flex', gap: '0.3rem', padding: '0.6rem 1rem', alignItems: 'center' }}>
                  <Scale size={14} style={{ animation: 'pulse 1.5s infinite', marginRight: '0.4rem' }} /> Analyzing legal texts...
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-bar">
            <button className={`btn-icon ${isListening ? 'listening' : ''}`} onClick={startSpeech} disabled={loading}>
              <Mic size={20} color={isListening ? '#ef4444' : 'currentColor'} />
            </button>
            <input
              value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder={isTransliterating ? "Romanizing Urdu..." : "Ask about Pakistani Law..."}
              disabled={loading || isTransliterating}
            />
            {isUrdu(input) && (
              <div className="input-indicator transliterating">
                <Languages size={14} /> Romanizing
              </div>
            )}
            <button className="chat-send-btn" onClick={() => handleSend()} disabled={loading || !input.trim() || isTransliterating}>
              <Send size={16} /> Send
            </button>
          </div>
        </div>

        <div className="bot-sidebar-panel">
          <div style={{ background: 'rgba(217, 70, 239, 0.05)', padding: '1rem', borderRadius: 12, border: '1px solid rgba(217, 70, 239, 0.1)', marginBottom: '1rem' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', color: '#d946ef', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Scale size={18} /> Book Consultation
            </h4>
            <p style={{ fontSize: '0.75rem', marginBottom: '0.8rem', opacity: 0.8 }}>Request professional legal representation.</p>

            <BookingForm token={token} />
          </div>

          <h4>Example Questions</h4>
          {['What is Section 144?', 'Rights of arrested person', 'What is bail under PPC?', 'Tenant eviction law Pakistan', 'Property inheritance rules', 'What is FIR procedure?'].map(q => (
            <button key={q} className="quick-btn" onClick={() => handleSend(q)}>{q}</button>
          ))}
          <hr style={{ border: 'none', borderTop: '1px solid var(--card-border)', margin: '0.5rem 0' }} />
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', lineHeight: 1.7 }}>
            <strong style={{ color: 'var(--text-color)' }}>ℹ️ Disclaimer</strong><br />
            This tool provides general legal guidance based on uploaded law books. It is not a substitute for professional legal advice.
          </div>
          <div style={{ marginTop: 'auto', paddingTop: '0.75rem' }}>
            <button className="quick-btn" onClick={clearChat} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', justifyContent: 'center' }}>
              <Trash2 size={14} /> Clear Chat
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function BookingForm({ token }) {
  const [formData, setFormData] = useState({ name: '', phone: '', email: '', notes: '' });
  const [status, setStatus] = useState({ loading: false, success: false, error: null });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name || !formData.phone || !formData.email) {
      setStatus({ ...status, error: 'Please fill in all fields' });
      return;
    }

    setStatus({ loading: true, success: false, error: null });
    try {
      const res = await fetch('/api/bot/lawbot/appointments', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      const data = await res.json();
      if (data.status === 'success') {
        setStatus({ loading: false, success: true, error: null });
        setFormData({ name: '', phone: '', email: '', notes: '' });
      } else {
        setStatus({ loading: false, success: false, error: data.message || 'Failed to book' });
      }
    } catch (err) {
      setStatus({ loading: false, success: false, error: 'Connection failed' });
    }
  };

  if (status.success) {
    return (
      <div style={{ textAlign: 'center', color: '#10b981', fontSize: '0.85rem', padding: '1rem 0' }}>
        <div style={{ fontSize: '1.5rem', marginBottom: '0.4rem' }}>✅</div>
        Consultation Requested!<br />Check your email for details.
        <button className="btn btn-sm btn-outline" style={{ marginTop: '1rem', width: '100%' }} onClick={() => setStatus({ success: false })}>New Request</button>
      </div>
    );
  }

  return (
    <form className="booking-mini-form" onSubmit={handleSubmit}>
      <input
        type="text" placeholder="Full Name" value={formData.name}
        onChange={e => setFormData({ ...formData, name: e.target.value })}
      />
      <input
        type="text" placeholder="Phone" value={formData.phone}
        onChange={e => setFormData({ ...formData, phone: e.target.value })}
      />
      <input
        type="email" placeholder="Email Address" value={formData.email}
        onChange={e => setFormData({ ...formData, email: e.target.value })}
      />
      <textarea
        placeholder="Case Notes..." value={formData.notes} rows="2"
        onChange={e => setFormData({ ...formData, notes: e.target.value })}
      />
      <button className="btn btn-primary" style={{ width: '100%', marginTop: '0.5rem' }} disabled={status.loading}>
        {status.loading ? 'Requesting...' : 'Request Consultation'}
      </button>
      {status.error && <div style={{ color: '#ef4444', fontSize: '0.7rem', marginTop: '0.4rem' }}>{status.error}</div>}
    </form>
  );
}
