import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, UserPlus, Users, CalendarCheck, MessageCircle,
  ArrowLeft, LogOut, Loader2, Plus, Trash2, Edit, Search, Send,
  HeartPulse, Clock, Phone, Mail, MapPin, CheckCircle2, XCircle,
  Activity, Stethoscope, Filter
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const BOT_API = '/api/bot/firstaid';

export default function SehatStaffDashboard({ token }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [staffVerified, setStaffVerified] = useState(sessionStorage.getItem('sehat_staff_verified') === 'true');
  const [staffAuth, setStaffAuth] = useState({ username: '', password: '', error: '' });
  const [authLoading, setAuthLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ summary: null, trends: null, doctors: [], patients: [], appointments: [] });
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const handleStaffLogin = async (e) => {
    e.preventDefault();
    setAuthLoading(true);
    setStaffAuth(prev => ({ ...prev, error: '' }));
    try {
      const res = await fetch(`${BOT_API}/staff/auth/login`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ username: staffAuth.username, password: staffAuth.password })
      });
      const d = await res.json();
      if (res.ok) {
        setStaffVerified(true);
        sessionStorage.setItem('sehat_staff_verified', 'true');
      } else {
        setStaffAuth(prev => ({ ...prev, error: d.detail || 'Login failed' }));
      }
    } catch (err) {
      setStaffAuth(prev => ({ ...prev, error: 'Network error occurred' }));
    } finally {
      setAuthLoading(false);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'dashboard') {
        const [sumRes, trendRes] = await Promise.all([
          fetch(`${BOT_API}/staff/analytics/summary`, { headers }),
          fetch(`${BOT_API}/staff/analytics/trends`, { headers }),
        ]);
        const sum = await sumRes.json();
        const trend = await trendRes.json();
        setData(p => ({ ...p, summary: sum.summary, trends: trend }));
      } else if (activeTab === 'doctors') {
        const res = await fetch(`${BOT_API}/staff/doctors`, { headers });
        const d = await res.json();
        setData(p => ({ ...p, doctors: d.doctors || [] }));
      } else if (activeTab === 'patients') {
        const res = await fetch(`${BOT_API}/staff/patients`, { headers });
        const d = await res.json();
        setData(p => ({ ...p, patients: d.patients || [] }));
      } else if (activeTab === 'appointments') {
        const res = await fetch(`${BOT_API}/staff/appointments`, { headers });
        const d = await res.json();
        setData(p => ({ ...p, appointments: d.appointments || [] }));
      }
    } catch (e) { console.error('Fetch error:', e); }
    finally { setLoading(false); }
  };

  useEffect(() => { 
    if (!staffVerified) {
      setLoading(false);
      return;
    }
    fetchData(); 
  }, [activeTab, staffVerified]);

  const navItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { id: 'doctors', icon: Stethoscope, label: 'Doctors' },
    { id: 'patients', icon: Users, label: 'Patients' },
    { id: 'appointments', icon: CalendarCheck, label: 'Appointments' },
    { id: 'chat', icon: MessageCircle, label: 'Staff AI' },
  ];

  if (!staffVerified) {
    return (
      <div className="staff-gate-wrapper">
         <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="auth-gate-card">
            <div className="gate-icon-wrap" style={{background:'rgba(59,130,246,0.1)', color:'#3b82f6'}}><HeartPulse size={36} /></div>
            <h2>Medical Staff Lock</h2>
            <p>Verify your healthcare professional credentials to access the hospital management vault.</p>
            
            <form onSubmit={handleStaffLogin} className="staff-auth-form">
              <div className="input-field-wrap">
                <Users size={18} />
                <input 
                  type="text" 
                  placeholder="Staff Username" 
                  value={staffAuth.username} 
                  onChange={e => setStaffAuth({...staffAuth, username: e.target.value})}
                  required
                />
              </div>
              <div className="input-field-wrap">
                <Clock size={18} />
                <input 
                  type="password" 
                  placeholder="Staff Password" 
                  value={staffAuth.password} 
                  onChange={e => setStaffAuth({...staffAuth, password: e.target.value})}
                  required
                />
              </div>
              {staffAuth.error && <div className="auth-error-msg">{staffAuth.error}</div>}
              <button type="submit" className="login-submit-btn" disabled={authLoading} style={{background:'#3b82f6'}}>
                {authLoading ? <Loader2 className="animate-spin" size={20} /> : 'Unlock Medical Vault'}
              </button>
              <button type="button" onClick={() => navigate('/dashboard')} className="cancel-auth-btn">
                Exit to Dashboard
              </button>
            </form>
         </motion.div>
      </div>
    );
  }

  return (
    <div className="staff-layout">
      <div className="staff-sidebar">
        <div className="staff-sidebar-header">
          <HeartPulse className="staff-logo" style={{ color: '#3b82f6' }} />
          <span>Sehat Staff</span>
        </div>
        <nav className="staff-nav">
          {navItems.map(item => (
            <button key={item.id} onClick={() => setActiveTab(item.id)}
              className={`staff-nav-item ${activeTab === item.id ? 'active' : ''}`}>
              <item.icon size={18} /><span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="staff-sidebar-footer">
          <button onClick={() => navigate('/bot/firstaid')} className="staff-nav-item">
            <ArrowLeft size={18} /><span>Patient Portal</span>
          </button>
          <button onClick={() => {
            sessionStorage.removeItem('sehat_staff_verified');
            setStaffVerified(false);
          }} className="staff-nav-item" style={{ color: '#f87171' }}>
            <LogOut size={18} /><span>Lock Panel</span>
          </button>
          <button onClick={() => navigate('/dashboard')} className="staff-nav-item">
            <ArrowLeft size={18} /><span>Exit</span>
          </button>
        </div>
      </div>

      <div className="staff-main">
        <header className="staff-header">
          <div className="staff-header-left">
            <h1>{navItems.find(n => n.id === activeTab)?.label}</h1>
            <p className="text-muted">Hospital Management System</p>
          </div>
          <div className="staff-header-right">
            <div className="staff-status-pill"><div className="status-dot online" /><span>System Online</span></div>
          </div>
        </header>
        <main className="staff-content-area">
          <AnimatePresence mode="wait">
            <motion.div key={activeTab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
              <div className="tab-content">
                {loading && activeTab !== 'chat' ? <div className="staff-loading"><Loader2 className="animate-spin" size={48} /></div> : <>
                  {activeTab === 'dashboard' && <DashboardTab summary={data.summary} trends={data.trends} />}
                  {activeTab === 'doctors' && <DoctorsTab doctors={data.doctors} refresh={fetchData} token={token} headers={headers} />}
                  {activeTab === 'patients' && <PatientsTab patients={data.patients} />}
                  {activeTab === 'appointments' && <AppointmentsTab appointments={data.appointments} refresh={fetchData} headers={headers} />}
                  {activeTab === 'chat' && <StaffChat token={token} />}
                </>}
              </div>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

/* ═══ DASHBOARD TAB ═══ */
function DashboardTab({ summary, trends }) {
  if (!summary) return <div className="empty-state"><Activity size={48} opacity={0.2} /><h3>No Data Yet</h3><p>Data appears once appointments are booked.</p></div>;
  const kpis = [
    { label: 'Total Patients', value: summary.total_patients, color: '#3b82f6' },
    { label: "Today's Appointments", value: summary.today_appointments, color: '#10b981' },
    { label: 'Active Doctors', value: summary.active_doctors, color: '#8b5cf6' },
    { label: 'Completion Rate', value: `${summary.completion_rate}%`, color: '#f59e0b' },
    { label: 'Confirmed', value: summary.confirmed, color: '#06b6d4' },
    { label: 'Completed', value: summary.completed, color: '#22c55e' },
    { label: 'Cancelled', value: summary.cancelled, color: '#ef4444' },
    { label: 'Total Appointments', value: summary.total_appointments, color: '#ec4899' },
  ];
  return (
    <div className="analytics-container">
      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {kpis.map((k, i) => (
          <div className="kpi-card" key={i}>
            <label>{k.label}</label>
            <div className="value" style={{ color: k.color }}>{k.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══ DOCTORS TAB ═══ */
function DoctorsTab({ doctors, refresh, token, headers }) {
  const [showAdd, setShowAdd] = useState(false);
  const [editDoc, setEditDoc] = useState(null);
  const [form, setForm] = useState({ doctor_name: '', specialty: '', availability_start: '09:00', availability_end: '17:00', available_days: ['Mon','Tue','Wed','Thu','Fri'], location: 'Main Hospital', contact_phone: '', contact_email: '', status: 'active' });

  const resetForm = () => setForm({ doctor_name: '', specialty: '', availability_start: '09:00', availability_end: '17:00', available_days: ['Mon','Tue','Wed','Thu','Fri'], location: 'Main Hospital', contact_phone: '', contact_email: '', status: 'active' });

  const handleSave = async (e) => {
    e.preventDefault();
    const url = editDoc ? `${BOT_API}/staff/doctors/${editDoc.doctor_id}` : `${BOT_API}/staff/doctors`;
    const method = editDoc ? 'PUT' : 'POST';
    try {
      const res = await fetch(url, { method, headers, body: JSON.stringify(form) });
      if (res.ok) { setShowAdd(false); setEditDoc(null); resetForm(); refresh(); }
    } catch (e) { console.error(e); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this doctor?')) return;
    try {
      await fetch(`${BOT_API}/staff/doctors/${id}`, { method: 'DELETE', headers });
      refresh();
    } catch (e) { console.error(e); }
  };

  const openEdit = (doc) => {
    setForm({ doctor_name: doc.doctor_name, specialty: doc.specialty, availability_start: doc.availability_start || '09:00', availability_end: doc.availability_end || '17:00', available_days: doc.available_days || ['Mon','Tue','Wed','Thu','Fri'], location: doc.location || '', contact_phone: doc.contact_phone || '', contact_email: doc.contact_email || '', status: doc.status || 'active' });
    setEditDoc(doc);
    setShowAdd(true);
  };

  const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const toggleDay = (d) => setForm(p => ({ ...p, available_days: p.available_days.includes(d) ? p.available_days.filter(x => x !== d) : [...p.available_days, d] }));

  return (
    <div className="menu-container">
      <div className="tab-actions">
        <button onClick={() => { resetForm(); setEditDoc(null); setShowAdd(true); }} className="btn-primary"><Plus size={16} /> Add Doctor</button>
      </div>

      {showAdd && (
        <div className="modal-overlay">
          <form className="staff-modal" onSubmit={handleSave} style={{ maxWidth: 520 }}>
            <h3>{editDoc ? 'Edit Doctor' : 'Add New Doctor'}</h3>
            <div className="form-group"><label>Doctor Name</label><input required value={form.doctor_name} onChange={e => setForm({ ...form, doctor_name: e.target.value })} placeholder="Dr. Ahmed Khan" /></div>
            <div className="form-row">
              <div className="form-group"><label>Specialty</label><input required value={form.specialty} onChange={e => setForm({ ...form, specialty: e.target.value })} placeholder="Cardiologist" /></div>
              <div className="form-group"><label>Status</label>
                <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} style={{ padding: '0.6rem', borderRadius: 8, background: 'var(--input-bg)', color: 'white', border: '1px solid var(--card-border)', width: '100%' }}>
                  <option value="active">Active</option><option value="on-leave">On Leave</option><option value="inactive">Inactive</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group"><label>Available From</label><input type="time" value={form.availability_start} onChange={e => setForm({ ...form, availability_start: e.target.value })} /></div>
              <div className="form-group"><label>Available Until</label><input type="time" value={form.availability_end} onChange={e => setForm({ ...form, availability_end: e.target.value })} /></div>
            </div>
            <div className="form-group">
              <label>Available Days</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {DAYS.map(d => (
                  <button type="button" key={d} onClick={() => toggleDay(d)}
                    style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer',
                      background: form.available_days.includes(d) ? 'rgba(59,130,246,0.2)' : 'transparent',
                      borderColor: form.available_days.includes(d) ? '#3b82f6' : 'var(--card-border)',
                      color: form.available_days.includes(d) ? '#60a5fa' : 'var(--text-muted)' }}>{d}</button>
                ))}
              </div>
            </div>
            <div className="form-group"><label>Location</label><input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} /></div>
            <div className="form-row">
              <div className="form-group"><label>Phone</label><input value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} placeholder="+92-300-0000000" /></div>
              <div className="form-group"><label>Email</label><input value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} placeholder="doctor@hospital.pk" /></div>
            </div>
            <div className="modal-actions">
              <button type="button" onClick={() => { setShowAdd(false); setEditDoc(null); }}>Cancel</button>
              <button type="submit" className="btn-save">{editDoc ? 'Update' : 'Add'} Doctor</button>
            </div>
          </form>
        </div>
      )}

      <div className="menu-table-wrap">
        <table className="staff-table">
          <thead><tr><th>Doctor</th><th>Specialty</th><th>Hours</th><th>Days</th><th>Location</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {doctors.map((doc, i) => (
              <tr key={i}>
                <td><strong>{doc.doctor_name}</strong>{doc.contact_phone && <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{doc.contact_phone}</div>}</td>
                <td>{doc.specialty}</td>
                <td style={{ fontSize: '0.8rem' }}>{doc.availability_start || '09:00'} – {doc.availability_end || '17:00'}</td>
                <td style={{ fontSize: '0.7rem' }}>{(doc.available_days || []).join(', ')}</td>
                <td style={{ fontSize: '0.8rem' }}>{doc.location}</td>
                <td><span className={`pill ${doc.status === 'active' ? 'online' : doc.status === 'on-leave' ? 'away' : 'offline'}`}>{doc.status || 'active'}</span></td>
                <td><div className="table-actions">
                  <button className="icon-btn" onClick={() => openEdit(doc)}><Edit size={14} /></button>
                  <button className="icon-btn" onClick={() => handleDelete(doc.doctor_id)}><Trash2 size={14} /></button>
                </div></td>
              </tr>
            ))}
            {doctors.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>No doctors found. Add your first doctor above.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══ PATIENTS TAB ═══ */
function PatientsTab({ patients }) {
  const [search, setSearch] = useState('');
  const filtered = patients.filter(p => !search || (p.name || '').toLowerCase().includes(search.toLowerCase()) || (p.email || '').toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="menu-container">
      <div className="tab-actions" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--input-bg)', borderRadius: 10, padding: '0.5rem 1rem', border: '1px solid var(--card-border)', flex: 1, maxWidth: 400 }}>
          <Search size={16} color="var(--text-muted)" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search patients..." style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', flex: 1, fontSize: '0.9rem' }} />
        </div>
      </div>
      <div className="menu-table-wrap">
        <table className="staff-table">
          <thead><tr><th>Patient</th><th>Phone</th><th>Email</th><th>Visits</th><th>Conditions</th><th>Last Visit</th></tr></thead>
          <tbody>
            {filtered.map((p, i) => (
              <tr key={i}>
                <td><strong>{p.name || 'N/A'}</strong></td>
                <td style={{ fontSize: '0.85rem' }}>{p.phone || '—'}</td>
                <td style={{ fontSize: '0.8rem' }}>{p.email || '—'}</td>
                <td><span className="pill online">{p.total_appointments}</span></td>
                <td style={{ fontSize: '0.75rem' }}>{(p.emergency_types || []).join(', ')}</td>
                <td style={{ fontSize: '0.8rem' }}>{p.last_visit ? new Date(p.last_visit).toLocaleDateString() : '—'}</td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>No patient records found.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══ APPOINTMENTS TAB ═══ */
function AppointmentsTab({ appointments, refresh, headers }) {
  const [filter, setFilter] = useState('');

  const updateStatus = async (id, newStatus) => {
    try {
      await fetch(`${BOT_API}/staff/appointments/${id}/status`, { method: 'PATCH', headers, body: JSON.stringify({ status: newStatus }) });
      refresh();
    } catch (e) { console.error(e); }
  };

  const filtered = appointments.filter(a => !filter || a.status === filter);
  const statusColors = { 'Confirmed': '#3b82f6', 'In Progress': '#f59e0b', 'Completed': '#22c55e', 'Cancelled': '#ef4444', 'No Show': '#6b7280' };

  return (
    <div className="menu-container">
      <div className="tab-actions" style={{ gap: 8, flexWrap: 'wrap' }}>
        {['', 'Confirmed', 'In Progress', 'Completed', 'Cancelled'].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
              background: filter === s ? 'rgba(59,130,246,0.15)' : 'transparent',
              borderColor: filter === s ? '#3b82f6' : 'var(--card-border)',
              color: filter === s ? '#60a5fa' : 'var(--text-muted)' }}>
            {s || 'All'}
          </button>
        ))}
      </div>
      <div className="menu-table-wrap" style={{ marginTop: '1rem' }}>
        <table className="staff-table">
          <thead><tr><th>Patient</th><th>Doctor</th><th>Type</th><th>Booked</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map((a, i) => (
              <tr key={i}>
                <td><strong>{a.patient?.name || 'N/A'}</strong><div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{a.patient?.phone}</div></td>
                <td style={{ fontSize: '0.85rem' }}>{a.doctor_name}</td>
                <td style={{ fontSize: '0.8rem' }}>{a.emergency_type}</td>
                <td style={{ fontSize: '0.8rem' }}>{a.booked_at ? new Date(a.booked_at).toLocaleDateString() : '—'}</td>
                <td><span style={{ padding: '3px 10px', borderRadius: 6, fontSize: '0.7rem', fontWeight: 700, background: `${statusColors[a.status] || '#6b7280'}22`, color: statusColors[a.status] || '#6b7280', border: `1px solid ${statusColors[a.status] || '#6b7280'}44` }}>{a.status}</span></td>
                <td><div className="table-actions" style={{ gap: 4 }}>
                  {a.status === 'Confirmed' && <button className="icon-btn" title="Start" onClick={() => updateStatus(a.appointment_id || a._id, 'In Progress')} style={{ color: '#f59e0b' }}><Activity size={14} /></button>}
                  {(a.status === 'Confirmed' || a.status === 'In Progress') && <button className="icon-btn" title="Complete" onClick={() => updateStatus(a.appointment_id || a._id, 'Completed')} style={{ color: '#22c55e' }}><CheckCircle2 size={14} /></button>}
                  {a.status !== 'Cancelled' && a.status !== 'Completed' && <button className="icon-btn" title="Cancel" onClick={() => updateStatus(a.appointment_id || a._id, 'Cancelled')} style={{ color: '#ef4444' }}><XCircle size={14} /></button>}
                </div></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>No appointments found.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══ STAFF AI CHAT ═══ */
function StaffChat({ token }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput('');
    setMessages(p => [...p, { role: 'user', content: msg }]);
    setLoading(true);
    try {
      const res = await fetch(`${BOT_API}/staff/chat`, { method: 'POST', headers, body: JSON.stringify({ message: msg, history: messages.slice(-5) }) });
      const d = await res.json();
      setMessages(p => [...p, { role: 'bot', content: d.reply }]);
    } catch (e) { setMessages(p => [...p, { role: 'bot', content: 'Error connecting to AI.' }]); }
    setLoading(false);
  };

  const quickActions = [
    "How many appointments today?",
    "Show all active doctors",
    "List patients this week",
    "Which doctor has most appointments?",
    "Add Dr. Ali, General Physician, 9am-5pm",
  ];

  return (
    <div className="staff-chat-container">
      {messages.length === 0 && (
        <div className="chat-welcome">
          <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>🏥</div>
          <h3>Hospital AI Copilot</h3>
          <p>Ask me to manage doctors, query patients, check appointments, or get analytics — all in natural language.</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: '1rem', justifyContent: 'center' }}>
            {quickActions.map(q => (
              <button key={q} onClick={() => setInput(q)} style={{ padding: '6px 12px', borderRadius: 8, background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#60a5fa', fontSize: '0.75rem', cursor: 'pointer' }}>{q}</button>
            ))}
          </div>
        </div>
      )}
      <div className="staff-chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
            </div>
          </div>
        ))}
        {loading && <div className="msg bot"><div className="bubble">Thinking...</div></div>}
        <div ref={endRef} />
      </div>
      <div className="chat-input-bar">
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} placeholder="Ask AI: manage doctors, query patients, analytics..." />
        <button onClick={handleSend} disabled={loading} className="chat-send-btn"><Send size={16} /> Send</button>
      </div>
    </div>
  );
}
