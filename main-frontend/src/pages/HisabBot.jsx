import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Trash2, RefreshCw } from 'lucide-react';
import { motion } from 'framer-motion';

const API = '/api/bot/hisabot';

function fmt(val) {
  if (val == null) return 'Rs 0';
  const v = parseFloat(val);
  return `Rs ${v.toLocaleString('en-PK', { maximumFractionDigits: v === Math.floor(v) ? 0 : 2 })}`;
}
function fmtN(val) { return val != null ? parseInt(val).toLocaleString() : '0'; }
function rankBadge(i) { const cls = {1:'rank-1',2:'rank-2',3:'rank-3'}[i] || 'rank-other'; return <span className={`rank-badge ${cls}`}>{i}</span>; }
function profitPill(val) {
  if (val == null) return 'N/A';
  const v = parseFloat(val);
  return <span className={`profit-pill ${v >= 0 ? 'profit-up' : 'profit-dn'}`}>{v >= 0 ? '▲' : '▼'} {fmt(Math.abs(v))}</span>;
}

// ── Report Section Component ────────────────────────────────────
function ReportSection({ title, subtitle, children, empty }) {
  return (
    <div className="report-card" style={empty ? {borderColor:'rgba(255,255,255,0.04)'} : {}}>
      <div className="section-header">{title}</div>
      <div style={{fontSize:'0.72rem', color:'var(--text-muted)', marginBottom:'0.8rem'}}>{subtitle}</div>
      <div>{children}</div>
    </div>
  );
}

// ── Report View ─────────────────────────────────────────────────
function ReportView({ token }) {
  const [tab, setTab] = useState('daily');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [schedule, setSchedule] = useState(null);
  const headers = { 'Authorization': `Bearer ${token}` };

  useEffect(() => {
    fetch(`${API}/report/schedule`, { headers }).then(r => r.json()).then(setSchedule).catch(() => {});
  }, []);

  const loadReport = async (period) => {
    setTab(period); setLoading(true); setData(null);
    try {
      const res = await fetch(`${API}/report/${period}`, { headers });
      const d = await res.json();
      setData(d);
    } catch { setData(null); }
    setLoading(false);
  };

  const sales = data?.sales;
  const prods = data?.top_products || [];
  const stock = data?.stock || [];
  const low = data?.low_stock || [];
  const paysDetail = data?.payments_detail || [];
  const pays = data?.payments;
  const pending = data?.pending || [];
  const customers = data?.top_customers || [];
  const pp = data?.product_profit || [];
  const sv = data?.stock_value;

  return (
    <div className="report-container">
      <div className="report-tabs">
        {['daily','weekly','monthly'].map(p => (
          <button key={p} className={`report-tab ${tab === p ? 'active' : ''}`} onClick={() => loadReport(p)}>
            {p === 'daily' ? '📅 Daily' : p === 'weekly' ? '📆 Weekly' : '🗓️ Monthly'}
          </button>
        ))}
      </div>

      {!data && !loading && (
        <div className="coming-soon">
          <div className="cs-icon">📊</div>
          <h3>Select a report period above</h3>
          <p>{schedule?.[tab]?.message || 'Click a tab to generate the report'}</p>
          <button className="btn btn-primary" style={{marginTop:'1rem'}} onClick={() => loadReport(tab)}>
            Generate {tab.charAt(0).toUpperCase() + tab.slice(1)} Report
          </button>
        </div>
      )}

      {loading && (
        <div className="coming-soon">
          <div className="cs-icon" style={{animation:'pulse 1.5s infinite'}}>⏳</div>
          <h3>{tab.charAt(0).toUpperCase() + tab.slice(1)} report tayar ho rahi hai...</h3>
        </div>
      )}

      {data && (
        <>
          <div className="report-card">
            <div className="report-header-text">HISABBOT · {tab.toUpperCase()} REPORT</div>
            <div className="report-title">{tab === 'daily' ? 'Roz ka' : tab === 'weekly' ? 'Hafte ka' : 'Mahine ka'} Business Report</div>
            <div className="report-sub">{data.date_label} · Generated: {data.generated_at}</div>
          </div>

          {/* Sales Summary */}
          <ReportSection title="💰 Sales Summary" subtitle="Is period ki kul sales, revenue aur net profit overview">
            {sales ? (
              <div className="kpi-grid">
                <div className="kpi-card"><div className="kpi-label">Total Orders</div><div className="kpi-value kpi-blue">{fmtN(sales.total_orders)}</div></div>
                <div className="kpi-card"><div className="kpi-label">Units Biki</div><div className="kpi-value kpi-purple">{fmtN(sales.total_qty)}</div></div>
                <div className="kpi-card"><div className="kpi-label">Kul Wasool</div><div className="kpi-value kpi-yellow">{fmt(sales.total_revenue)}</div></div>
                <div className="kpi-card"><div className="kpi-label">Kul Lagat</div><div className="kpi-value" style={{color:'#9ca3af'}}>{fmt(sales.total_cost)}</div></div>
                <div className="kpi-card"><div className="kpi-label">Net Profit</div><div className={`kpi-value ${parseFloat(sales.total_profit) >= 0 ? 'kpi-green' : 'kpi-red'}`}>{parseFloat(sales.total_profit) >= 0 ? '▲' : '▼'} {fmt(Math.abs(parseFloat(sales.total_profit)))}</div></div>
                <div className="kpi-card"><div className="kpi-label">Margin %</div><div className={`kpi-value ${(sales.total_revenue ? (sales.total_profit/sales.total_revenue)*100 : 0) >= 0 ? 'kpi-green' : 'kpi-red'}`}>{sales.total_revenue ? ((sales.total_profit/sales.total_revenue)*100).toFixed(1) : 0}%</div></div>
              </div>
            ) : <span style={{color:'var(--text-muted)'}}>Is period mein koi sale nahi hui.</span>}
          </ReportSection>

          {/* Top Products */}
          {prods.length > 0 && (
            <ReportSection title="🏆 Top Products" subtitle="Sabse zyada bikne wale products">
              <table className="rpt-table">
                <thead><tr><th>#</th><th>Product</th><th>Qty</th><th>Revenue</th><th>Profit</th></tr></thead>
                <tbody>{prods.map((p,i) => (
                  <tr key={i}><td>{rankBadge(i+1)}</td><td style={{fontWeight:600,color:'#f1f5f9'}}>{(p._id||'?').replace(/\b\w/g,c=>c.toUpperCase())}</td><td style={{color:'#a78bfa'}}>{fmtN(p.qty)} units</td><td style={{color:'#fbbf24'}}>{fmt(p.revenue)}</td><td>{profitPill(p.profit)}</td></tr>
                ))}</tbody>
              </table>
            </ReportSection>
          )}

          {/* Stock Status */}
          {stock.length > 0 && (
            <ReportSection title="📦 Stock Status" subtitle="Har product ki current inventory">
              {stock.map((item,i) => {
                const qty = Math.max(0, item.qty || 0);
                const thr = item.low_stock_threshold || 5;
                const isLow = qty <= thr;
                const barPct = Math.min(100, (qty / Math.max(thr*3,1)) * 100);
                return (
                  <div key={i} className={`stock-row ${isLow ? 'low' : ''}`}>
                    <div style={{flex:1}}>
                      <span style={{fontWeight:600,color:'#f1f5f9'}}>{(item.product||'?').replace(/\b\w/g,c=>c.toUpperCase())}</span>
                      {isLow ? <span className="alert-pill" style={{marginLeft:'0.5rem'}}>⚠ Low</span> : <span className="ok-pill" style={{marginLeft:'0.5rem'}}>✓ OK</span>}
                      <span className="stock-bar-wrap"><span className="stock-bar" style={{width:`${barPct}%`,background:isLow?'#f87171':'#34d399'}} /></span>
                    </div>
                    <div style={{textAlign:'right',whiteSpace:'nowrap'}}>
                      <div style={{fontFamily:'"JetBrains Mono",monospace',fontSize:'0.9rem',fontWeight:700,color:isLow?'#f87171':'#f1f5f9'}}>{fmtN(qty)} <span style={{fontSize:'0.6rem',color:'var(--text-muted)'}}>units</span></div>
                    </div>
                  </div>
                );
              })}
            </ReportSection>
          )}

          {/* Low Stock Alerts */}
          <ReportSection title="🚨 Low Stock Alerts" subtitle={low.length > 0 ? `${low.length} item(s) critical level par` : 'Stock alert status'}>
            {low.length > 0 ? low.map((item,i) => (
              <span key={i} className="alert-pill" style={{margin:'0.15rem 0.25rem'}}>⚠ {(item.product||'?').replace(/\b\w/g,c=>c.toUpperCase())}: {fmtN(Math.max(0,item.qty||0))} baca</span>
            )) : <span className="ok-pill">✅ Sab items ka stock theek hai</span>}
          </ReportSection>

          {/* Payments */}
          <ReportSection title="💚 Payments Received" subtitle="Is period mein customers ne jo payments diye">
            {paysDetail.length > 0 ? paysDetail.map((c,i) => (
              <div key={i} className="cust-card" style={{borderColor:'rgba(16,185,129,0.2)'}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
                  <div><div className="cust-name">💚 {(c._id||'?').replace(/\b\w/g,l=>l.toUpperCase())}</div><div className="cust-addr">📍 {c.address||'—'} · 📞 {c.phone||'—'}</div></div>
                  <div style={{fontSize:'1.2rem',fontWeight:700,color:'#34d399',whiteSpace:'nowrap'}}>{fmt(c.total)}</div>
                </div>
              </div>
            )) : <span style={{color:'var(--text-muted)'}}>Koi payment nahi aaya.</span>}
          </ReportSection>

          {/* Pending */}
          {pending.length > 0 && (
            <ReportSection title="🔴 Outstanding Balance" subtitle="Jo customers abhi tak payment nahi diye">
              {pending.map((c,i) => (
                <div key={i} className="cust-card" style={{borderColor:'rgba(245,158,11,0.3)',background:'rgba(245,158,11,0.03)'}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
                    <div><div className="cust-name">🔴 {(c.name||'?').replace(/\b\w/g,l=>l.toUpperCase())}</div><div className="cust-addr">📍 {c.address||c.area||'—'} · 📞 {c.phone||c.contact||'—'}</div></div>
                    <div style={{fontSize:'1.2rem',fontWeight:700,color:'#fbbf24',whiteSpace:'nowrap'}}>{fmt(c.total_credit)}</div>
                  </div>
                </div>
              ))}
            </ReportSection>
          )}

          {/* Top Customers */}
          {customers.length > 0 && (
            <ReportSection title="👥 Top Customers" subtitle="Sabse zyada kharidari karne wale">
              <table className="rpt-table">
                <thead><tr><th>#</th><th>Customer</th><th>Spend</th><th>Orders</th><th>Profit</th></tr></thead>
                <tbody>{customers.map((c,i) => (
                  <tr key={i}><td>{rankBadge(i+1)}</td><td style={{fontWeight:600,color:'#f1f5f9'}}>{(c._id||'?').replace(/\b\w/g,l=>l.toUpperCase())}</td><td style={{color:'#fbbf24'}}>{fmt(c.spent)}</td><td style={{color:'#60a5fa'}}>{fmtN(c.orders)}</td><td>{profitPill(c.profit)}</td></tr>
                ))}</tbody>
              </table>
            </ReportSection>
          )}

          {/* Product Profit */}
          {pp.length > 0 && (
            <ReportSection title="📈 Profit & Loss — Per Product" subtitle="Har product ka munafa ya nuqsan">
              <table className="rpt-table">
                <thead><tr><th>Product</th><th>Qty</th><th>Revenue</th><th>Cost</th><th>Profit</th><th>Margin</th></tr></thead>
                <tbody>{pp.map((p,i) => {
                  const margin = p.revenue ? ((p.profit/p.revenue)*100).toFixed(1) : '0';
                  return <tr key={i}><td style={{fontWeight:600,color:'#f1f5f9'}}>{(p._id||'?').replace(/\b\w/g,l=>l.toUpperCase())}</td><td style={{color:'#a78bfa'}}>{fmtN(p.qty)}</td><td style={{color:'#fbbf24'}}>{fmt(p.revenue)}</td><td style={{color:'#9ca3af'}}>{fmt(p.cost)}</td><td>{profitPill(p.profit)}</td><td style={{color:parseFloat(margin)>=0?'#34d399':'#f87171',fontFamily:'"JetBrains Mono",monospace'}}>{margin}%</td></tr>;
                })}</tbody>
              </table>
            </ReportSection>
          )}

          {/* Inventory Value */}
          {sv && (
            <ReportSection title="🏪 Inventory Value" subtitle="Stock ki kul qeemat at cost price">
              <div className="kpi-grid" style={{gridTemplateColumns:'repeat(3,1fr)'}}>
                <div className="kpi-card"><div className="kpi-label">Products</div><div className="kpi-value kpi-blue">{fmtN(sv.total_items)}</div></div>
                <div className="kpi-card"><div className="kpi-label">Total Units</div><div className="kpi-value kpi-purple">{fmtN(sv.total_units)}</div></div>
                <div className="kpi-card"><div className="kpi-label">Stock Value</div><div className="kpi-value kpi-yellow">{fmt(sv.total_value)}</div></div>
              </div>
            </ReportSection>
          )}

          <div style={{display:'flex',justifyContent:'flex-end',marginTop:'0.5rem'}}>
            <button className="btn btn-outline" onClick={() => loadReport(tab)} style={{borderRadius:10,fontSize:'0.82rem'}}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────
export default function HisabBot({ token }) {
  const navigate = useNavigate();
  const [page, setPage] = useState('chat');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ total:0, writes:0, reads:0 });
  const messagesEndRef = useRef(null);
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const addMsg = (role, content, extra = {}) => {
    setMessages(prev => [...prev, { role, content, time: new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'}), ...extra }]);
    setStats(prev => ({ ...prev, total: prev.total + 1 }));
  };

  const handleSend = async (text) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    setInput('');
    addMsg('user', msg);
    setLoading(true);
    try {
      const history = messages.slice(-4).filter(m => !m.isError).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }));
      const res = await fetch(`${API}/chat`, { method:'POST', headers, body: JSON.stringify({ message: msg, history }) });
      const data = await res.json();
      if (data.error) { addMsg('bot', data.error, { isError:true }); }
      else {
        const intent = data.intent?.intent || '';
        if (intent === 'write') setStats(prev => ({...prev, writes: prev.writes+1}));
        if (intent === 'read') setStats(prev => ({...prev, reads: prev.reads+1}));
        addMsg('bot', data.reply, { intent });
      }
    } catch (err) { addMsg('bot', `Error: ${err.message}`, { isError:true }); }
    setLoading(false);
  };

  const quickCmds = [
    ['📦 Stock check','poora stock batao'], ['📊 Aaj ki sale','aaj ki total sale batao'],
    ['💰 Aaj ka profit','aaj ka munafa kitna hua'], ['👥 Customers','kaunse customers ka baaki hai'],
    ['📈 Is mahine','is mahine ki total sale aur profit'], ['🔍 Top product','kaunsa product sabse zyada bikta hai'],
  ];

  const intentBadge = (intent) => {
    const cls = {write:'write',read:'read',unknown:'chat'}[intent] || 'read';
    return <span className={`intent-badge ${cls}`}>{intent}</span>;
  };

  return (
    <motion.div className="bot-page" initial={{opacity:0}} animate={{opacity:1}} transition={{duration:0.3}}>
      <div className="bot-topbar">
        <div className="bot-topbar-left">
          <button className="btn btn-outline" onClick={() => navigate('/dashboard')} style={{padding:'0.4rem 0.8rem',borderRadius:8}}><ArrowLeft size={16}/> Back</button>
          <div className="bot-status-dot" style={{background:'#34d399',boxShadow:'0 0 10px #34d399'}} />
          <span style={{fontWeight:600,fontSize:'1.05rem'}}>🧾 HisabBot Workspace</span>
        </div>
        <div className="page-tabs">
          <button className={`page-tab ${page==='chat'?'active':''}`} onClick={() => setPage('chat')}>💬 Chat</button>
          <button className={`page-tab ${page==='report'?'active':''}`} onClick={() => setPage('report')}>📊 Reports</button>
        </div>
      </div>

      {page === 'chat' ? (
        <div className="bot-body">
          <div className="bot-main">
            <div className="chat-messages">
              {messages.length === 0 && (
                <div className="chat-welcome">
                  <div className="chat-welcome-icon">🧾</div>
                  <h3>HisabBot ready hai</h3>
                  <p>Roman Urdu mein apna sawaal ya hukum likhein</p>
                </div>
              )}
              {messages.map((msg,i) => (
                <div key={i} className={`msg-row ${msg.role==='user'?'user-row':''}`}>
                  <div className={`msg-avatar ${msg.role==='user'?'user-avatar-sm':'bot-avatar'}`}>{msg.role==='user'?'You':'🧾'}</div>
                  <div>
                    <div className={`msg-bubble ${msg.role==='user'?'user-bubble':msg.isError?'error-bubble':'bot-bubble'}`}>
                      <div style={{whiteSpace:'pre-wrap'}}>{msg.content}</div>
                    </div>
                    {msg.intent && !msg.isError && intentBadge(msg.intent)}
                    <div className="msg-time">{msg.time}</div>
                  </div>
                </div>
              ))}
              {loading && <div className="msg-row"><div className="msg-avatar bot-avatar">🧾</div><div className="msg-bubble bot-bubble" style={{padding:'0.6rem 1rem'}}>Agent soch raha hai...</div></div>}
              <div ref={messagesEndRef} />
            </div>
            <div className="chat-input-bar">
              <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&handleSend()} placeholder="Roman Urdu mein likhein... (e.g. ali ko 50 bag cheeni 3550 per bag diya)" disabled={loading} />
              <button className="chat-send-btn" onClick={()=>handleSend()} disabled={loading||!input.trim()}><Send size={16}/> Send</button>
            </div>
          </div>

          <div className="bot-sidebar-panel">
            <h4>Session Stats</h4>
            <div className="stat-box"><div className="stat-label">Total Messages</div><div className="stat-value stat-blue">{stats.total}</div></div>
            <div className="stat-box"><div className="stat-label">Write Ops</div><div className="stat-value stat-purple">{stats.writes}</div></div>
            <div className="stat-box"><div className="stat-label">Read Queries</div><div className="stat-value stat-green">{stats.reads}</div></div>
            <hr style={{border:'none',borderTop:'1px solid var(--card-border)',margin:'0.5rem 0'}} />
            <h4>Quick Commands</h4>
            {quickCmds.map(([label,cmd]) => (
              <button key={label} className="quick-btn" onClick={() => handleSend(cmd)}>{label}</button>
            ))}
            <hr style={{border:'none',borderTop:'1px solid var(--card-border)',margin:'0.5rem 0'}} />
            <button className="quick-btn" onClick={() => { setMessages([]); setStats({total:0,writes:0,reads:0}); }} style={{display:'flex',alignItems:'center',gap:'0.4rem',justifyContent:'center'}}>
              <Trash2 size={14}/> Clear Chat
            </button>
          </div>
        </div>
      ) : (
        <ReportView token={token} />
      )}
    </motion.div>
  );
}
