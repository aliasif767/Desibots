import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Trash2, Mic, Languages } from 'lucide-react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = '/api/bot/firstaid/api/v1';
const BACKEND_BASE = '/api/bot/firstaid';

function getInitials(name) {
  return name.replace('Dr. ', '').replace('(', '').split(' ').map(p => p[0]?.toUpperCase()).join('').slice(0,2);
}

function fmtTime(iso) {
  try {
    const dt = new Date(iso);
    return dt.toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) + ' — ' + dt.toLocaleTimeString('en-US', { hour:'numeric', minute:'2-digit' });
  } catch { return iso; }
}

function detectIntent(text) {
  const t = text.toLowerCase();
  if (['book','appointment','schedule','reserve'].some(w => t.includes(w))) return 'book';
  if (['doctor','available','availability','specialist','find doctor'].some(w => t.includes(w))) return 'check_doctor';
  if (['yes','confirm','sure','ok','okay','proceed','go ahead','correct'].some(w => t.includes(w))) return 'confirm';
  if (['no','cancel','skip','stop','abort'].some(w => t.includes(w))) return 'cancel';
  return 'emergency';
}

// ── Rich Card Components ────────────────────────────────────────
function EmergencyCard({ data }) {
  const isHigh = data.acuity === 'high';
  const isDB = data.source === 'database';
  const et = data.emergency_type || '';
  const sub = data.subtype || '';
  const steps = data.steps || [];
  const answer = data.answer || '';
  const notes = data.notes || '';
  const image = data.image || '';

  return (
    <div>
      {isHigh && (
        <div className="emergency-banner">
          <span className="banner-icon">🚨</span>
          <div>
            <strong>CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY</strong>
            <span>Contact emergency services first — administer first aid while help is on the way.</span>
          </div>
        </div>
      )}
      <div className="et-header">
        <div className="et-title">{et}{sub ? ` — ${sub}` : ''}</div>
        <div className="et-source">{isDB ? 'Verified medical database' : 'AI-generated guidance (Groq LLM)'}</div>
        <div className="badge-row">
          <span className={`acuity-badge ${isHigh ? 'acuity-high' : 'acuity-low'}`}>● {isHigh ? 'High' : 'Low'} Acuity</span>
          <span className={`acuity-badge ${isDB ? 'source-db' : 'source-llm'}`}>{isDB ? '✓ Verified DB' : '⚡ AI Guidance'}</span>
        </div>
      </div>
      <hr className="card-divider" />
      {isDB && steps.length > 0 ? (
        <ul className="step-list">
          {steps.map((s, i) => (
            <li key={i} className="step-item">
              <div className={`step-num ${isHigh ? 'high' : 'low'}`}>{s.step_number}</div>
              <div className="step-text">
                {s.instruction}
                {isHigh && i === steps.length - 1 && (
                  <div style={{ fontSize:'0.7rem', color:'#FF6B7A', marginTop:'0.3rem', fontWeight:600 }}>
                    ⚠ If person loses consciousness — call emergency services immediately.
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : answer ? (
        <div className="markdown-content ai-answer"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown></div>
      ) : null}
      {image && (
        <>
          <div className="firstaid-img-wrap">
            <img src={image} alt={`First aid — ${et}`} />
          </div>
          <div className="img-caption">📷 Illustrated first aid reference</div>
        </>
      )}
      {notes && <div className={`note-callout ${isHigh ? 'note-high' : 'note-low'}`}>{notes}</div>}
      <hr className="card-divider" />
      <div className="followup-hint">Ask a follow-up, or say <b>"check doctor availability"</b> to find a nearby specialist.</div>
    </div>
  );
}

function DoctorCard({ doc, onBook }) {
  const initials = getInitials(doc.doctor_name || 'Doctor');
  const days = Array.isArray(doc.available_days) ? doc.available_days.join(', ') : doc.available_days;
  
  return (
    <div className="doc-card">
      <div className="doc-card-label">Recommended Specialist</div>
      <div className="doc-row">
        <div className="doc-avatar">{initials}</div>
        <div>
          <div className="doc-name">{doc.doctor_name}</div>
          <div className="doc-specialty">{doc.specialty || 'Medical Specialist'}</div>
          <div className="doc-loc">📍 {doc.location}</div>
        </div>
      </div>
      <div className="doc-meta-grid">
        <div className="doc-meta-item"><div className="doc-meta-label">Availability</div><div className="doc-meta-val" style={{color:'#34d399'}}>{doc.availability || 'Available Now'}</div></div>
        <div className="doc-meta-item"><div className="doc-meta-label">Booking Status</div><div className="doc-meta-val" style={{color:'#60a5fa'}}>{doc.appointment_status || 'Ready to Book'}</div></div>
        {days && <div className="doc-meta-item full"><div className="doc-meta-label">Working Days</div><div className="doc-meta-val">{days}</div></div>}
        {doc.appointment_time && <div className="doc-meta-item full"><div className="doc-meta-label">Next Available Slot</div><div className="doc-meta-val" style={{color:'#60a5fa'}}>{fmtTime(doc.appointment_time)}</div></div>}
      </div>
      {onBook ? (
        <button onClick={() => onBook(doc)} style={{marginTop:'0.8rem', width:'100%', padding:'0.6rem', background:'#3b82f6', color:'white', border:'none', borderRadius:'6px', cursor:'pointer', fontWeight:'bold'}}>
          Book Appointment
        </button>
      ) : (
        <div className="book-cta">Say <b>"book appointment"</b> to reserve this slot — I'll collect your details.</div>
      )}
    </div>
  );
}

function ConfirmedCard({ booking, patient }) {
  const initials = getInitials(booking.doctor_name || 'Doctor');
  return (
    <div className="confirmed-card">
      <div className="confirmed-title"><span>✅</span> Appointment Confirmed</div>
      <div className="doc-row" style={{marginBottom:'0.6rem'}}>
        <div className="doc-avatar" style={{background:'linear-gradient(135deg,#2ECC8F,#1A8F5F)'}}>{initials}</div>
        <div><div className="doc-name">{booking.doctor_name}</div><div className="doc-loc">📍 {booking.location}</div></div>
      </div>
      <hr className="card-divider" />
      <div className="confirmed-detail">
        <b>Patient</b>&nbsp;&nbsp; {patient.name}<br/>
        <b>Phone</b>&nbsp;&nbsp;&nbsp;&nbsp; {patient.phone}<br/>
        <b>Email</b>&nbsp;&nbsp;&nbsp;&nbsp; {patient.email}<br/>
        <b>Scheduled</b> {booking.appointment_time ? fmtTime(booking.appointment_time) : 'To be confirmed'}
      </div>
      <div className="confirmed-footer">📋 Your details have been saved. The hospital team will contact you shortly to confirm.</div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────
export default function FirstAidBot({ token }) {
  const navigate = useNavigate();

  // ── Persistence Logic ──────────────────────────────────────────
  const storageKey = `firstaid_bot_state_${token.slice(-10)}`;
  
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
  const [bookingState, setBookingState] = useState(saved.bookingState || null);
  const [bookingInfo, setBookingInfo] = useState(saved.bookingInfo || {});
  const [pendingDoctor, setPendingDoctor] = useState(saved.pendingDoctor || null);
  const [lastEmergency, setLastEmergency] = useState(saved.lastEmergency || null);
  
  const messagesEndRef = useRef(null);
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Sync to localStorage
  useEffect(() => {
    const stateToSave = { messages, bookingState, bookingInfo, pendingDoctor, lastEmergency };
    localStorage.setItem(storageKey, JSON.stringify(stateToSave));
  }, [messages, bookingState, bookingInfo, pendingDoctor, lastEmergency]);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // Show welcome on first load
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{ role: 'bot', type: 'welcome' }]);
    }
  }, []);

  const addMsg = (role, content, extra = {}) => {
    setMessages(prev => [...prev, { role, content, time: new Date().toLocaleTimeString('en-US', {hour:'2-digit',minute:'2-digit',second:'2-digit'}), ...extra }]);
  };

  const apiAssess = async (query) => {
    const res = await fetch(`${API_BASE}/emergency`, { method:'POST', headers, body: JSON.stringify({query}) });
    if (!res.ok) throw new Error('Backend error');
    return res.json();
  };

  const apiCheckDoctor = async (emergencyType, queryText = "") => {
    try {
      const url = `${API_BASE}/doctors/available?type=${encodeURIComponent(emergencyType)}&query=${encodeURIComponent(queryText)}`;
      const res = await fetch(url, { headers });
      if (!res.ok) return null;
      return res.json();
    } catch { return null; }
  };

  const apiBookAppointment = async (doctorId, patient, emergencyType) => {
    try {
      const res = await fetch(`${API_BASE}/appointments`, { method:'POST', headers, body: JSON.stringify({ doctor_id: doctorId, emergency_type: emergencyType, ...patient }) });
      if (!res.ok) return null;
      return res.json();
    } catch { return null; }
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
      // Booking state machine
      if (bookingState === 'ask_name') {
        setBookingInfo(prev => ({ ...prev, name: text }));
        setBookingState('ask_phone');
        addMsg('bot', '📞 What is your phone number?');
        return;
      }
      if (bookingState === 'ask_phone') {
        setBookingInfo(prev => ({ ...prev, phone: text }));
        setBookingState('ask_email');
        addMsg('bot', '📧 And your email address?');
        return;
      }
      if (bookingState === 'ask_email') {
        const info = { ...bookingInfo, email: text };
        setBookingInfo(info);
        setBookingState('confirm');
        addMsg('bot', `Please review your details:\n\n👤 Name: ${info.name}\n📞 Phone: ${info.phone}\n📧 Email: ${text}\n🩺 Doctor: ${pendingDoctor?.doctor_name || ''}\n\nType **confirm** to book, or **cancel** to abort.`);
        return;
      }
      if (bookingState === 'confirm') {
        const intent = detectIntent(text);
        if (intent === 'confirm') {
          const result = await apiBookAppointment(pendingDoctor?.doctor_id || 'mock_001', bookingInfo, lastEmergency || 'general');
          const booking = result || pendingDoctor || {};
          addMsg('bot', '', { type: 'confirmed', booking, patient: bookingInfo });
        } else {
          addMsg('bot', '❌ Booking cancelled. Feel free to ask anything else.');
        }
        setBookingState(null); setBookingInfo({}); setPendingDoctor(null);
        return;
      }

      // Intent routing
      let intent = detectIntent(text);

      if (intent === 'book') {
        if (!pendingDoctor) {
          addMsg('bot', "Let me check doctor availability for your condition first...");
          const et = lastEmergency || 'general';
          const result = await apiCheckDoctor(et, text);
          let docs = result?.doctors || [];
          if (docs.length > 0) {
            setPendingDoctor(docs[0]);
            addMsg('bot', '', { type: 'doctors', doctors: docs });
          } else {
            addMsg('bot', "I couldn't find a specific doctor matching your request. Would you like to see all available doctors?");
          }
          return;
        } else {
          setBookingState('ask_name');
          addMsg('bot', `Let's book an appointment with **${pendingDoctor.doctor_name}**.\n\n👤 What is your **full name**?`);
          return;
        }
      }

      if (intent === 'check_doctor') {
        const et = lastEmergency || 'general';
        const result = await apiCheckDoctor(et, text);
        let docs = result?.doctors || [];
        
        if (docs.length === 0) {
          addMsg('bot', "I couldn't find a doctor specifically matching your request. Let me show you the generally available doctors.");
          const fallbackResult = await apiCheckDoctor(et, "");
          docs = fallbackResult?.doctors || [];
        }
        
        if (docs.length === 0) {
          docs = [{
            doctor_name: 'Dr. Sarah Chen (Cardiologist)', availability: 'Available Now',
            appointment_status: 'Ready to Book', location: 'City General Hospital — 1.2 miles away',
            appointment_time: new Date(Date.now() + 86400000).toISOString(), doctor_id: 'mock_001',
          }];
        }
        setPendingDoctor(docs[0]);
        addMsg('bot', '', { type: 'doctors', doctors: docs });
        return;
      }

      // Emergency query
      const data = await apiAssess(text);
      const et = (data.emergency_type || '').toLowerCase().replace(/ /g, '_');
      setLastEmergency(et);
      addMsg('bot', '', { type: 'emergency', data });

    } catch (err) {
      addMsg('bot', `⚠️ ${err.message || 'Cannot reach the backend. Please ensure FastAPI is running.'}`, { isError: true });
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([{ role: 'bot', type: 'welcome' }]);
    setBookingState(null); setBookingInfo({}); setPendingDoctor(null); setLastEmergency(null);
    localStorage.removeItem(storageKey);
  };

  return (
    <motion.div className="bot-page" initial={{opacity:0}} animate={{opacity:1}} transition={{duration:0.3}}>
      <div className="bot-topbar">
        <div className="bot-topbar-left">
          <button className="btn btn-outline" onClick={() => navigate('/dashboard')} style={{padding:'0.4rem 0.8rem', borderRadius:8}}>
            <ArrowLeft size={16} /> Back
          </button>
          <div className="bot-status-dot" style={{background:'#10b981', boxShadow:'0 0 10px #10b981'}} />
          <span style={{fontWeight:600, fontSize:'1.05rem'}}>Sehat Bot Workspace</span>
        </div>
      </div>

      <div className="bot-body">
        <div className="bot-main">
          <div className="chat-messages">
            {messages.map((msg, i) => {
              if (msg.type === 'welcome') {
                return (
                  <div key={i} className="chat-welcome">
                    <div className="chat-welcome-icon">🏥</div>
                    <h3>Hello — I'm your AI First Aid Assistant.</h3>
                    <p>Describe any medical emergency and I'll give you verified, step-by-step first aid guidance, connect you with a specialist, and help you book an appointment.</p>
                   
                  </div>
                );
              }
              return (
                <div key={i} className={`msg-row ${msg.role === 'user' ? 'user-row' : ''}`}>
                  <div className={`msg-avatar ${msg.role === 'user' ? 'user-avatar-sm' : 'bot-avatar'}`}>
                    {msg.role === 'user' ? 'You' : '🏥'}
                  </div>
                  <div className={`msg-bubble ${msg.role === 'user' ? 'user-bubble' : msg.isError ? 'error-bubble' : 'bot-bubble'}`}>
                    {msg.type === 'emergency' && <EmergencyCard data={msg.data} />}
                    {msg.type === 'doctors' && (
                      <div style={{display:'flex', flexDirection:'column', gap:'0.8rem'}}>
                        <div style={{fontWeight:600}}>Found {msg.doctors.length} available doctor{msg.doctors.length > 1 ? 's' : ''}:</div>
                        {msg.doctors.map((d, idx) => (
                          <DoctorCard 
                            key={idx} 
                            doc={d} 
                            onBook={(selectedDoc) => {
                              setPendingDoctor(selectedDoc);
                              setBookingState('ask_name');
                              addMsg('bot', `Let's book an appointment with **${selectedDoc.doctor_name}**.\n\n👤 What is your **full name**?`);
                            }} 
                          />
                        ))}
                      </div>
                    )}
                    {msg.type === 'doctor' && <DoctorCard doc={msg.doctor} />}
                    {msg.type === 'confirmed' && <ConfirmedCard booking={msg.booking} patient={msg.patient} />}
                    {!msg.type && msg.content && <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>}
                  </div>
                </div>
              );
            })}
            {loading && (
              <div className="msg-row">
                <div className="msg-avatar bot-avatar">🏥</div>
                <div className="msg-bubble bot-bubble" style={{display:'flex',gap:'0.3rem',padding:'0.6rem 1rem'}}>
                  <span style={{animation:'pulse 1.5s infinite'}}>●</span>
                  <span style={{animation:'pulse 1.5s infinite 0.2s'}}>●</span>
                  <span style={{animation:'pulse 1.5s infinite 0.4s'}}>●</span>
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
              placeholder={isTransliterating ? "Romanizing Urdu..." : "Describe the emergency…"}
              disabled={loading || isTransliterating}
            />
            {isUrdu(input) && (
              <div className="input-indicator transliterating" style={{fontSize:'0.65rem', color:'#f87171', display:'flex', alignItems:'center', gap:'0.2rem', padding:'0 0.5rem'}}>
                <Languages size={12} /> Romanizing...
              </div>
            )}
            <button className="chat-send-btn" onClick={() => handleSend()} disabled={loading || !input.trim() || isTransliterating}>
              <Send size={16} /> Send
            </button>
          </div>
        </div>

        <div className="bot-sidebar-panel">
          <h4>🏥 Hospital Staff</h4>
          <button className="quick-btn" onClick={() => navigate('/bot/firstaid/staff')} style={{background:'rgba(59,130,246,0.12)', border:'1px solid rgba(59,130,246,0.3)', color:'#60a5fa', fontWeight:600}}>
            Open Staff Panel →
          </button>

          <h4 style={{marginTop:'0.75rem'}}>Quick Scenarios</h4>
          {['Someone is choking','Heart attack symptoms','Child fell and hurt head','Severe burn injury','Snake bite first aid','Allergic reaction','Fracture or broken bone'].map(cmd => (
            <button key={cmd} className="quick-btn" onClick={() => { setInput(cmd); }}>{cmd}</button>
          ))}

          <h4 style={{marginTop:'0.5rem'}}>Patient Tools</h4>
          <button className="quick-btn" onClick={() => { setInput('Check my symptom: headache and fever'); }} style={{fontSize:'0.78rem'}}>🩺 Symptom Checker</button>
          <button className="quick-btn" onClick={() => { setInput('Check doctor availability'); }} style={{fontSize:'0.78rem'}}>👨‍⚕️ Find a Doctor</button>
          <button className="quick-btn" onClick={() => { setInput('Book an appointment'); }} style={{fontSize:'0.78rem'}}>📅 Book Appointment</button>

          <h4 style={{marginTop:'0.5rem'}}>You Can Say</h4>
          <div style={{fontSize:'0.75rem', color:'var(--text-muted)', lineHeight:2, fontStyle:'italic'}}>
            "What do I do for a heart attack?"<br/>"Check doctor availability"<br/>"Book an appointment"<br/>"Check my symptoms"<br/>"Is CPR safe for children?"
          </div>
          <div style={{marginTop:'auto', paddingTop:'0.75rem'}}>
            <button className="quick-btn" onClick={clearChat} style={{display:'flex',alignItems:'center',gap:'0.4rem',justifyContent:'center'}}>
              <Trash2 size={14} /> Clear Conversation
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
