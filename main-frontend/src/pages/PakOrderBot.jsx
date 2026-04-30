import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Send, Trash2, X, ClipboardList } from 'lucide-react';
import { motion } from 'framer-motion';

const API = '/api/bot/pakorder';

function stripHtml(t) { return String(t).replace(/<[^>]*>/g, '').trim(); }

function intentBadge(intent) {
  const m = {
    order_place:['order','order'], menu_read:['menu','menu'], offers_read:['menu','offers'],
    order_track:['track','track'], order_cancel:['menu','cancel'], conversation:['chat','chat'],
    feedback_write:['track','feedback'], popular_items:['menu','popular']
  };
  const [cls, lbl] = m[intent] || ['chat', intent || 'chat'];
  return <span className={`intent-badge ${cls}`}>{lbl}</span>;
}

function parseOrder(reply) {
  const oidM = reply.match(/Order\s*ID\s*[:#\s]+#?(PKT-\w+)/i);
  const etaM = reply.match(/ETA\s*[~:\s]*~?\s*(\d+)\s*min/i);
  const totalM = reply.match(/TOTAL\s+Rs\s+([\d,]+)/i);
  const items = [];
  for (const line of reply.split('\n')) {
    const m = line.match(/^\s{1,6}(\d+)x\s+(.+?)\s{2,}Rs\s+[\d,]+/);
    if (m) items.push(`${m[1]}x ${m[2].trim()}`);
  }
  if (!oidM) return null;
  const etaTotal = etaM ? parseInt(etaM[1]) : 30;
  return {
    order_id: oidM[1], prep_time: Math.max(5, etaTotal - 10), delivery_time: 10,
    eta_minutes: etaTotal, items_str: items.join(', ') || '—',
    total: totalM ? totalM[1] : '—', placed_at: Date.now() / 1000,
    dismissed: false, db_status: 'received', status_ts: null,
  };
}

// ── Order Tracker Component ─────────────────────────────────────
function OrderTracker({ order, apiUrl, token, onDismiss, canAccessStaff }) {
  const [status, setStatus] = useState(order.db_status || 'received');
  const [statusTs, setStatusTs] = useState(order.status_ts);
  const [now, setNow] = useState(Date.now() / 1000);
  const headers = { 'Authorization': `Bearer ${token}` };

  // Poll status every 10s
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${apiUrl}/order-status/${order.order_id}`, { headers });
        if (res.ok) {
          const d = await res.json();
          if (d.status) setStatus(d.status);
          if (d.status_ts) setStatusTs(d.status_ts);
        }
      } catch {}
    };
    poll();
    const iv = setInterval(poll, 10000);
    return () => clearInterval(iv);
  }, [order.order_id]);

  // Tick every second
  useEffect(() => {
    const iv = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(iv);
  }, []);

  const prepSec = (order.prep_time || 20) * 60;
  const delivSec = (order.delivery_time || 10) * 60;
  const totalSec = prepSec + delivSec;
  const elapsed = statusTs ? Math.max(0, now - statusTs) : 0;

  let remaining = 0, phaseLabel = '', overallPct = 0, stage = '';

  if (status === 'received') {
    stage = 'waiting'; phaseLabel = 'Restaurant confirm kar raha hai...';
    overallPct = 2; remaining = order.eta_minutes * 60;
  } else if (status === 'preparing') {
    stage = 'preparing'; remaining = Math.max(0, prepSec - elapsed);
    overallPct = Math.min(99, (elapsed / totalSec) * 100); phaseLabel = 'Khana tayar ho raha hai';
  } else if (status === 'ready') {
    stage = 'preparing'; remaining = Math.max(0, 120 - elapsed);
    overallPct = Math.min(99, (prepSec / totalSec) * 100); phaseLabel = 'Khana ready! Dispatch ho raha hai...';
  } else if (status === 'dispatched') {
    stage = 'onway'; remaining = Math.max(0, delivSec - elapsed);
    overallPct = Math.min(99, ((prepSec + elapsed) / totalSec) * 100); phaseLabel = 'Order raste mein hai!';
  } else {
    stage = 'delivered'; remaining = 0; overallPct = 100;
  }

  const rm = Math.floor(remaining / 60);
  const rs = Math.floor(remaining % 60);
  const pad = n => String(Math.floor(Math.max(0, n))).padStart(2, '0');

  let vehLeft;
  if (['received','preparing','ready'].includes(status)) vehLeft = 10;
  else if (status === 'delivered') vehLeft = 82;
  else vehLeft = 10 + Math.min(100, (elapsed / delivSec) * 100) / 100 * 72;

  const icon = status === 'dispatched' ? '🛵' : '👨‍🍳';

  const pillCls = (key) => {
    if (stage === key) return 'active';
    if ((key === 'preparing' && ['onway','delivered'].includes(stage)) || (key === 'onway' && stage === 'delivered')) return 'done';
    return '';
  };

  return (
    <div className="tracker-container">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
        <div>
          <div className="tracker-oid">#{order.order_id}</div>
          <div className="tracker-items">{order.items_str}</div>
          <div style={{fontSize:'0.75rem',color:'var(--text-muted)'}}>Rs {order.total}</div>
        </div>
        <button onClick={onDismiss} style={{background:'transparent',border:'none',color:'var(--text-muted)',cursor:'pointer',padding:'0.25rem'}}><X size={14}/></button>
      </div>

      {status === 'delivered' ? (
        <div style={{marginTop:'0.75rem'}}>
          <div className="tracker-done-text">Order Pahunch Gaya! 🎉</div>
          <div className="tracker-done-sub">Aapka khana deliver ho gaya. Maza karein!</div>
        </div>
      ) : (
        <>
          <div className="tracker-countdown">{pad(rm)}:{pad(rs)}</div>
          <div className="tracker-eta">{phaseLabel} · ~{order.eta_minutes} min total</div>
          <div className="tracker-progress-wrap"><div className="tracker-progress-fill" style={{width:`${overallPct.toFixed(1)}%`}} /></div>
          {/* Staff entry point — only if admin or subbed */}
          {canAccessStaff && (
            <Link to="/bot/pakorder/staff" className="staff-panel-btn">
              <ClipboardList size={18} />
              <span>Staff Dashboard</span>
            </Link>
          )}
          <div className="tracker-road">
            <div className="dashes" />
            <span className="shop-icon">🏪</span>
            <span className="vehicle" style={{left:`${vehLeft.toFixed(1)}%`}}>{icon}</span>
            <span className="home-icon">🏠</span>
          </div>
        </>
      )}

      <div className="tracker-pills">
        <span className={`tracker-pill ${pillCls('preparing')}`}>Tayari Ho Raha</span>
        <span className={`tracker-pill ${pillCls('onway')}`}>Raste Mein</span>
        <span className={`tracker-pill ${pillCls('delivered')}`}>Pahunch Gaya</span>
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────
export default function PakOrderBot({ token, role, subscribedBots = [] }) {
  const canAccessStaff = role === 'admin' || subscribedBots.includes('pakorder');
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [convStage, setConvStage] = useState('');
  const [orderDraft, setOrderDraft] = useState({});
  const [liveOrders, setLiveOrders] = useState([]);
  const [showTracker, setShowTracker] = useState(false);
  const [history, setHistory] = useState([]);
  const messagesEndRef = useRef(null);
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const addMsg = (role, content, extra = {}) => {
    const clean = role === 'bot' ? stripHtml(content) : content;
    setMessages(prev => [...prev, { role, content: clean, time: new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'}), ...extra }]);
    if (!extra.isError) {
      setHistory(prev => [...prev, { role: role === 'user' ? 'user' : 'assistant', content: clean }]);
    }
  };

  const handleSend = async (text) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    setInput('');
    addMsg('user', msg);
    setLoading(true);

    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST', headers,
        body: JSON.stringify({ message: msg, history, conv_stage: convStage, order_draft: orderDraft })
      });
      const data = await res.json();

      if (data.error) {
        addMsg('bot', data.error, { isError: true });
      } else {
        const reply = data.reply || 'Jawab nahi mila.';
        setConvStage(data.conv_stage || '');
        setOrderDraft(data.order_draft || {});

        const intentObj = data.intent || {};
        const iStr = intentObj.tasks?.[0]?.intent || '';

        // Check for confirmed order
        const isConfirmed = iStr === 'order_place' || reply.toUpperCase().includes('ORDER CONFIRMED') || (reply.includes('PKT-') && reply.includes('Order receive ho gaya'));
        if (isConfirmed) {
          const entry = parseOrder(reply);
          if (entry) {
            setLiveOrders(prev => {
              if (prev.some(o => o.order_id === entry.order_id)) return prev;
              return [...prev, entry];
            });
            setShowTracker(true);
          }
        }

        addMsg('bot', reply, { intent: iStr });
      }
    } catch (err) {
      addMsg('bot', `Error: ${err.message}`, { isError: true });
    }
    setLoading(false);
  };

  const stageLabels = {
    await_more: '🛒 Cart review', modifying: '✏️ Modifying cart',
    await_name: '📝 Naam darj karein', await_phone: '📱 Phone darj karein',
    await_address: '📍 Address darj karein', await_confirm: '✅ Confirm karein',
  };

  const activeOrders = liveOrders.filter(o => !o.dismissed);

  return (
    <motion.div className="bot-page" initial={{opacity:0}} animate={{opacity:1}} transition={{duration:0.3}}>
      <div className="bot-topbar">
        <div className="bot-topbar-left">
          <button className="btn btn-outline" onClick={() => navigate('/dashboard')} style={{padding:'0.4rem 0.8rem',borderRadius:8}}><ArrowLeft size={16}/> Back</button>
          <div className="bot-status-dot" style={{background:'#f59e0b',boxShadow:'0 0 10px #f59e0b'}} />
          <span style={{fontWeight:600,fontSize:'1.05rem'}}>🍛 PakOrderBot Workspace</span>
        </div>
        {activeOrders.length > 0 && (
          <button className="btn btn-outline" onClick={() => setShowTracker(!showTracker)} style={{borderRadius:10,fontSize:'0.82rem',borderColor:'rgba(16,185,129,0.3)',color:'#34d399'}}>
            🛵 Live Tracker ({activeOrders.length})
          </button>
        )}
      </div>

      <div className="bot-body">
        <div className="bot-main">
          {/* Live Tracker */}
          {showTracker && activeOrders.length > 0 && (
            <div style={{paddingTop:'0.75rem'}}>
              {activeOrders.map(order => (
                <OrderTracker
                  key={order.order_id}
                  order={order}
                  apiUrl={API}
                  token={token}
                  onDismiss={() => setLiveOrders(prev => prev.map(o => o.order_id === order.order_id ? {...o, dismissed:true} : o))}
                  canAccessStaff={canAccessStaff}
                />
              ))}
            </div>
          )}

          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-welcome">
                <div className="chat-welcome-icon">🍛</div>
                <h3>PakOrderBot mein khush aamdeed!</h3>
                <p style={{lineHeight:1.8}}>
                  Menu: "menu dikhao"<br/>Order: "2 chicken biryani order karo"<br/>Deals: "koi offers hain?"
                </p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`msg-row ${msg.role === 'user' ? 'user-row' : ''}`}>
                <div className={`msg-avatar ${msg.role === 'user' ? 'user-avatar-sm' : 'bot-avatar'}`}>
                  {msg.role === 'user' ? 'You' : '🍛'}
                </div>
                <div>
                  <div className={`msg-bubble ${msg.role === 'user' ? 'user-bubble' : msg.isError ? 'error-bubble' : 'bot-bubble'}`}>
                    <div style={{whiteSpace:'pre-wrap'}}>{msg.content}</div>
                  </div>
                  <div style={{display:'flex',gap:'0.5rem',alignItems:'center'}}>
                    {msg.intent && !msg.isError && intentBadge(msg.intent)}
                    <span className="msg-time">{msg.time}</span>
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="msg-row">
                <div className="msg-avatar bot-avatar">🍛</div>
                <div className="msg-bubble bot-bubble" style={{padding:'0.6rem 1rem'}}>...</div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-bar">
            <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} placeholder="Roman Urdu mein likhein..." disabled={loading} />
            <button className="chat-send-btn" onClick={() => handleSend()} disabled={loading || !input.trim()}><Send size={16}/> Send</button>
          </div>
        </div>

        <div className="bot-sidebar-panel">
          {convStage && (
            <div style={{background:'rgba(16,185,129,0.08)',border:'1px solid rgba(16,185,129,0.25)',borderRadius:8,padding:'0.4rem 0.6rem',fontSize:'0.75rem',color:'#34d399'}}>
              {stageLabels[convStage] || convStage}
            </div>
          )}
          <>
            <h4 style={{marginTop:'1.5rem', color:'#f59e0b'}}>🔒 Staff Portal</h4>
            <button 
              className="quick-btn staff-btn" 
              onClick={() => navigate('/bot/pakorder/staff')} 
              style={{borderColor:'rgba(245,158,11,0.5)', color:'#fbbf24', fontWeight:600}}
            >
              🔓 Open Management Panel
            </button>
            <p style={{fontSize:'0.7rem', color:'rgba(245,158,11,0.5)', marginTop:'0.5rem', textAlign:'center', lineHeight:'1.4'}}>
              Restaurant owners and staff can login here<br/>to manage orders & menu.
            </p>
            <hr style={{border:'none',borderTop:'1px solid var(--card-border)',margin:'1rem 0'}} />
          </>
          <h4>Customer Actions</h4>
          {[['🍽️ Menu','menu dikhao'],['🎉 Offers','koi offers ya deals hain?'],['📋 Track','mera order track karo'],['⭐ Feedback','feedback dena chahta hoon']].map(([label,cmd]) => (
            <button key={label} className="quick-btn" onClick={() => handleSend(cmd)}>{label}</button>
          ))}
          <hr style={{border:'none',borderTop:'1px solid var(--card-border)',margin:'0.5rem 0'}} />
          <div className="stat-box">
            <div className="stat-label">Messages</div>
            <div className="stat-value stat-green">{messages.length}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Orders Placed</div>
            <div className="stat-value stat-blue">{liveOrders.length}</div>
          </div>
          <div style={{marginTop:'auto',paddingTop:'0.75rem'}}>
            <button className="quick-btn" onClick={() => {
              setMessages([]); setHistory([]); setLiveOrders([]);
              setConvStage(''); setOrderDraft({}); setShowTracker(false);
            }} style={{display:'flex',alignItems:'center',gap:'0.4rem',justifyContent:'center'}}>
              <Trash2 size={14}/> Clear Chat
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
