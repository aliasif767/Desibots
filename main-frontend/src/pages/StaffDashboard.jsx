import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  LineChart, Line, PieChart, Pie, Cell, Legend, AreaChart, Area 
} from 'recharts';
import { 
  LayoutDashboard, ClipboardList, UtensilsCrossed, Gift, 
  MessageSquare, PieChart as ChartIcon, MessageCircle, 
  ArrowLeft, LogOut, ChevronRight, Clock, User, Phone, 
  MapPin, CheckCircle2, Package, Loader2, Plus, Trash2, Edit 
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const BOT_API = '/api/bot/pakorder';

export default function StaffDashboard({ token }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('orders');
  const [staffVerified, setStaffVerified] = useState(sessionStorage.getItem('staff_verified') === 'true');
  const [staffAuth, setStaffAuth] = useState({ username: '', password: '', error: '' });
  const [authLoading, setAuthLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    orders: [],
    menu: [],
    offers: [],
    feedback: [],
    analytics: null,
    history: []
  });
  const [unauthorized, setUnauthorized] = useState(false);

  const fetchData = async () => {
    try {
      const headers = { 'Authorization': `Bearer ${token}` };
      
      // Fetch based on active tab mostly, but some initial data
      if (activeTab === 'orders') {
        const res = await fetch(`${BOT_API}/staff/orders/live`, { headers });
        if (res.status === 403) { setUnauthorized(true); return; }
        const d = await res.json();
        setData(prev => ({ ...prev, orders: d.orders || [] }));
      } else if (activeTab === 'menu') {
        const res = await fetch(`${BOT_API}/staff/menu/all`, { headers });
        if (res.status === 403) { setUnauthorized(true); return; }
        const d = await res.json();
        setData(prev => ({ ...prev, menu: d.menu || [] }));
      } else if (activeTab === 'offers') {
        const res = await fetch(`${BOT_API}/staff/offers`, { headers });
        if (res.status === 403) { setUnauthorized(true); return; }
        const d = await res.json();
        setData(prev => ({ ...prev, offers: d.offers || [] }));
      } else if (activeTab === 'feedback') {
        const res = await fetch(`${BOT_API}/staff/feedback`, { headers });
        if (res.status === 403) { setUnauthorized(true); return; }
        const d = await res.json();
        setData(prev => ({ ...prev, feedback: d.feedback || [] }));
      } else if (activeTab === 'analytics') {
        const [sumRes, revRes, catRes] = await Promise.all([
          fetch(`${BOT_API}/staff/analytics/summary`, { headers }),
          fetch(`${BOT_API}/staff/analytics/revenue-chart`, { headers }),
          fetch(`${BOT_API}/staff/analytics/categories`, { headers })
        ]);
        if (sumRes.status === 403) { setUnauthorized(true); return; }
        const sum = await sumRes.json();
        const rev = await revRes.json();
        const cat = await catRes.json();
        setData(prev => ({ ...prev, analytics: { summary: sum.summary, today: sum.today_orders, revenue: rev.data, categories: cat.data } }));
      } else if (activeTab === 'history') {
        const res = await fetch(`${BOT_API}/staff/orders/history`, { headers });
        if (res.status === 403) { setUnauthorized(true); return; }
        const d = await res.json();
        setData(prev => ({ ...prev, history: d.orders || [] }));
      }
    } catch (err) {
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!staffVerified) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchData();
    
    // Auto refresh orders every 30s
    let interval;
    if (activeTab === 'orders') {
      interval = setInterval(fetchData, 30000);
    }
    return () => clearInterval(interval);
  }, [activeTab, staffVerified]);

  const handleStaffLogin = async (e) => {
    e.preventDefault();
    setAuthLoading(true);
    setStaffAuth(prev => ({ ...prev, error: '' }));
    try {
      const res = await fetch(`${BOT_API}/auth/login`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ username: staffAuth.username, password: staffAuth.password })
      });
      const d = await res.json();
      if (res.ok) {
        setStaffVerified(true);
        sessionStorage.setItem('staff_verified', 'true');
      } else {
        setStaffAuth(prev => ({ ...prev, error: d.detail || 'Login failed' }));
      }
    } catch (err) {
      setStaffAuth(prev => ({ ...prev, error: 'Network error occurred' }));
    } finally {
      setAuthLoading(false);
    }
  };

  const updateOrderStatus = async (orderId, newStatus) => {
    try {
      const res = await fetch(`${BOT_API}/staff/orders/${orderId}/status`, {
        method: 'PATCH',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status: newStatus })
      });
      if (res.ok) fetchData();
    } catch (err) { console.error(err); }
  };

  const deleteMenuItem = async (name) => {
    if (!window.confirm(`Delete ${name}?`)) return;
    try {
      const res = await fetch(`${BOT_API}/staff/menu/${encodeURIComponent(name)}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) fetchData();
    } catch (err) { console.error(err); }
  };

  const navItems = [
    { id: 'orders', icon: ClipboardList, label: 'Live Orders' },
    { id: 'history', icon: Package, label: 'History' },
    { id: 'menu', icon: UtensilsCrossed, label: 'Menu' },
    { id: 'offers', icon: Gift, label: 'Offers' },
    { id: 'analytics', icon: ChartIcon, label: 'Analytics' },
    { id: 'feedback', icon: MessageSquare, label: 'Feedback' },
    { id: 'chat', icon: MessageCircle, label: 'Staff AI' },
  ];

  if (unauthorized) {
    return (
      <div className="staff-gate-wrapper">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="auth-gate-card">
          <LogOut size={64} color="#f87171" style={{marginBottom:'1rem'}} />
          <h2>Access Denied</h2>
          <p>Please login as an authorized business owner or staff member to manage PakOrderBot.</p>
          <button onClick={() => navigate('/bot/pakorder')} className="login-submit-btn" style={{width:'100%'}}>Return to Customer Bot</button>
        </motion.div>
      </div>
    );
  }

  if (!staffVerified) {
    return (
      <div className="staff-gate-wrapper">
         <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="auth-gate-card">
            <div className="gate-icon-wrap"><UtensilsCrossed size={36} /></div>
            <h2>Staff Identity Lock</h2>
            <p>Enter your restaurant's staff credentials to unlock the management vault.</p>
            
            <form onSubmit={handleStaffLogin} className="staff-auth-form">
              <div className="input-field-wrap">
                <User size={18} />
                <input 
                  type="text" 
                  placeholder="Staff Username" 
                  value={staffAuth.username} 
                  onChange={e => setStaffAuth({...staffAuth, username: e.target.value})}
                  required
                />
              </div>
              <div className="input-field-wrap">
                <ClipboardList size={18} />
                <input 
                  type="password" 
                  placeholder="Staff Password" 
                  value={staffAuth.password} 
                  onChange={e => setStaffAuth({...staffAuth, password: e.target.value})}
                  required
                />
              </div>
              {staffAuth.error && <div className="auth-error-msg">{staffAuth.error}</div>}
              <button type="submit" className="login-submit-btn" disabled={authLoading}>
                {authLoading ? <Loader2 className="animate-spin" size={20} /> : 'Unlock Dashboard'}
              </button>
              <button type="button" onClick={() => navigate('/bot/pakorder')} className="cancel-auth-btn">
                Exit to Customer Bot
              </button>
            </form>
         </motion.div>
      </div>
    );
  }

  if (loading) return <div className="staff-loading"><Loader2 className="animate-spin" size={48} /></div>;

  return (
    <div className="staff-layout">
      {/* Sidebar */}
      <div className="staff-sidebar">
        <div className="staff-sidebar-header">
          <UtensilsCrossed className="staff-logo" />
          <span>Staff Panel</span>
        </div>
        
        <nav className="staff-nav">
          {navItems.map(item => (
            <button 
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`staff-nav-item ${activeTab === item.id ? 'active' : ''}`}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="staff-sidebar-footer">
          <button 
            onClick={() => {
              sessionStorage.removeItem('staff_verified');
              setStaffVerified(false);
            }} 
            className="staff-nav-item"
            style={{ color: '#f87171' }}
          >
            <LogOut size={18} />
            <span>Lock Dashboard</span>
          </button>
          <button onClick={() => navigate('/bot/pakorder')} className="staff-nav-item">
            <ArrowLeft size={18} />
            <span>Back to Customer Bot</span>
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="staff-main">
        <header className="staff-header">
          <div className="staff-header-left">
            <h1>{navItems.find(n => n.id === activeTab)?.label}</h1>
            <p className="text-muted">Real-time restaurant management</p>
          </div>
          <div className="staff-header-right">
            <div className="staff-status-pill">
              <div className="status-dot online" />
              <span>System Online</span>
            </div>
          </div>
        </header>

        <main className="staff-content-area">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              <div className="tab-content">
                {activeTab === 'orders' && <OrdersTab orders={data.orders} updateStatus={updateOrderStatus} />}
                {activeTab === 'history' && <HistoryTab history={data.history} />}
                {activeTab === 'menu' && <MenuTab menu={data.menu} deleteMenu={deleteMenuItem} refresh={fetchData} token={token} />}
                {activeTab === 'offers' && <OffersTab offers={data.offers} refresh={fetchData} token={token} />}
                {activeTab === 'analytics' && <AnalyticsTab analytics={data.analytics} />}
                {activeTab === 'feedback' && <FeedbackTab feedback={data.feedback} />}
                {activeTab === 'chat' && <StaffChat token={token} />}
              </div>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

function RenderTab({ tab, data, updateStatus, deleteMenu, token, refresh }) {
  switch (tab) {
    case 'orders': return <OrdersTab orders={data.orders} updateStatus={updateStatus} />;
    case 'menu':   return <MenuTab menu={data.menu} deleteMenu={deleteMenu} refresh={refresh} token={token} />;
    case 'analytics': return <AnalyticsTab analytics={data.analytics} />;
    case 'history': return <HistoryTab history={data.history} />;
    case 'feedback': return <FeedbackTab feedback={data.feedback} />;
    case 'offers': return <OffersTab offers={data.offers} refresh={refresh} token={token} />;
    case 'chat': return <StaffChat token={token} />;
    default: return <div>Coming Soon...</div>;
  }
}

// ── SUB-COMPONENTS ─────────────────────────────────────────────────────────

function OrdersTab({ orders, updateStatus }) {
  if (!orders || !orders.length) return (
    <div className="empty-state">
      <ClipboardList size={48} opacity={0.2} />
      <h3>No Active Orders</h3>
      <p>All queue is clear! Sit back and enjoy.</p>
    </div>
  );

  return (
    <div className="orders-grid">
      {orders.map(order => (
        <OrderCard key={order.order_id} order={order} updateStatus={updateStatus} />
      ))}
    </div>
  );
}

function OrderCard({ order, updateStatus }) {
  const getStatusColor = (s) => {
    const m = {
      received: 'status-blue',
      preparing: 'status-yellow',
      ready: 'status-green',
      dispatched: 'status-purple'
    };
    return m[s] || 'status-gray';
  };

  const items = order.items || [];
  const createdAt = new Date(order.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <motion.div className="staff-card order-card" layout>
      <div className="order-card-header">
        <span className="order-id">#{order.order_id}</span>
        <span className={`status-badge ${getStatusColor(order.status)}`}>
          {order.status.toUpperCase()}
        </span>
        <span className="order-time">{createdAt}</span>
      </div>
      
      <div className="order-items-list">
        {items.map((i, idx) => (
          <div key={idx} className="order-item-row">
            <span className="qty">{i.qty}x</span>
            <span className="name">{i.name}</span>
          </div>
        ))}
      </div>

      <div className="order-customer-info">
        <div className="info-row"><User size={14}/><span>{order.customer_name}</span></div>
        <div className="info-row"><Phone size={14}/><span>{order.customer_phone}</span></div>
        <div className="info-row"><MapPin size={14}/><span>{order.customer_address}</span></div>
      </div>

      <div className="order-footer">
        <div className="order-total">Rs {order.total_amount?.toLocaleString()}</div>
        <div className="order-actions">
          {order.status === 'received' && (
            <button onClick={() => updateStatus(order.order_id, 'preparing')} className="btn-action start">Confirm & Prep</button>
          )}
          {order.status === 'preparing' && (
            <button onClick={() => updateStatus(order.order_id, 'ready')} className="btn-action ready">Ready for Pickup</button>
          )}
          {order.status === 'ready' && (
            <button onClick={() => updateStatus(order.order_id, 'dispatched')} className="btn-action dispatch">Dispatch 🛵</button>
          )}
          {order.status === 'dispatched' && (
            <button onClick={() => updateStatus(order.order_id, 'delivered')} className="btn-action deliver">Mark Delivered</button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function MenuTab({ menu, deleteMenu, refresh, token }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newItem, setNewItem] = useState({ name: '', category: 'main course', price: '', description: '', available: true, prep_time: 20 });

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${BOT_API}/staff/menu`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newItem)
      });
      if (res.ok) {
        setShowAdd(false);
        refresh();
      }
    } catch (err) { console.error(err); }
  };

  return (
    <div className="menu-container">
      <div className="tab-actions">
        <button onClick={() => setShowAdd(true)} className="btn-primary">
          <Plus size={16} /> Add New Item
        </button>
      </div>

      {showAdd && (
        <div className="modal-overlay">
          <form className="staff-modal" onSubmit={handleSave}>
            <h3>Add Menu Item</h3>
            <div className="form-group"><label>Name</label><input required value={newItem.name} onChange={e => setNewItem({...newItem, name: e.target.value})} /></div>
            <div className="form-row">
              <div className="form-group"><label>Category</label><input required value={newItem.category} onChange={e => setNewItem({...newItem, category: e.target.value})} /></div>
              <div className="form-group"><label>Price (Rs)</label><input type="number" required value={newItem.price} onChange={e => setNewItem({...newItem, price: e.target.value})} /></div>
            </div>
            <div className="form-group"><label>Prep Time (min)</label><input type="number" value={newItem.prep_time} onChange={e => setNewItem({...newItem, prep_time: e.target.value})} /></div>
            <div className="form-group"><label>Description</label><textarea value={newItem.description} onChange={e => setNewItem({...newItem, description: e.target.value})} /></div>
            <div className="modal-actions">
              <button type="button" onClick={() => setShowAdd(false)}>Cancel</button>
              <button type="submit" className="btn-save">Save Item</button>
            </div>
          </form>
        </div>
      )}

      <div className="menu-table-wrap">
        <table className="staff-table">
          <thead>
            <tr>
              <th>Item Name</th>
              <th>Category</th>
              <th>Price</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {menu.map((item, i) => (
              <tr key={i}>
                <td><strong>{item.name}</strong></td>
                <td>{item.category}</td>
                <td>Rs {item.price}</td>
                <td>
                  <span className={`pill ${item.available ? 'online' : 'offline'}`}>
                    {item.available ? 'Available' : 'Disabled'}
                  </span>
                </td>
                <td>
                  <div className="table-actions">
                    <button className="icon-btn" onClick={() => deleteMenu(item.name)}><Trash2 size={14}/></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AnalyticsTab({ analytics }) {
  if (!analytics || !analytics.summary) return (
    <div className="empty-state">
      <ChartIcon size={48} opacity={0.2} />
      <h3>No Analytics Data</h3>
      <p>Data will appear once orders are processed.</p>
    </div>
  );

  const summary = analytics.summary;

  return (
    <div className="analytics-container">
      <div className="kpi-grid">
        <div className="kpi-card">
          <label>Total Orders (7d)</label>
          <div className="value">{summary.total_orders}</div>
        </div>
        <div className="kpi-card">
          <label>Total Revenue (7d)</label>
          <div className="value">Rs {summary.total_revenue?.toLocaleString()}</div>
        </div>
        <div className="kpi-card">
          <label>Today's Count</label>
          <div className="value">{analytics.today}</div>
        </div>
        <div className="kpi-card">
          <label>Avg Ticket</label>
          <div className="value">Rs {summary.avg_order?.toFixed(0)}</div>
        </div>
      </div>

      <div className="charts-grid">
        <div className="chart-card large">
          <h3>Revenue Trend (Last 7 Days)</h3>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={analytics.revenue}>
                <defs>
                  <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4c5ee8" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#4c5ee8" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" stroke="#2d3563" fontSize={10} />
                <YAxis stroke="#2d3563" fontSize={10} />
                <Tooltip contentStyle={{ background: '#0d1025', border: '1px solid #1a1e32', fontSize: 12 }} />
                <Area type="monotone" dataKey="revenue" stroke="#4c5ee8" fillOpacity={1} fill="url(#colorRev)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card">
          <h3>Category Breakdown</h3>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={analytics.categories}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="revenue"
                >
                  {analytics.categories.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={['#4c5ee8', '#fbbf24', '#34d399', '#a78bfa', '#f87171'][index % 5]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

function HistoryTab({ history }) {
  return (
    <div className="history-container">
      <div className="staff-table-wrap">
        <table className="staff-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Time</th>
              <th>Customer</th>
              <th>Status</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {history.map((o, i) => (
              <tr key={i}>
                <td><span className="oid-pill">#{o.order_id}</span></td>
                <td>{new Date(o.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                <td>{o.customer_name}</td>
                <td><span className={`status-pill ${o.status}`}>{o.status}</span></td>
                <td>Rs {o.total_amount?.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FeedbackTab({ feedback }) {
  return (
    <div className="feedback-list">
      {feedback.map((f, i) => {
        const name = f.customer_name || f.name || 'Anonymous';
        const msg = f.message || f.comment || f.text || f.feedback || '*(No text provided)*';
        const rating = f.rating || 0;
        const date = f.created_at ? new Date(f.created_at).toLocaleString() : '—';
        
        return (
          <div className="feedback-card" key={i}>
            <div className="flex-row">
              <div className="fb-author">
                <strong>{name}</strong>
                {f.customer_phone && <span className="fb-phone"> · {f.customer_phone}</span>}
              </div>
              <div className="stars">{"★".repeat(rating)}{"☆".repeat(5 - rating)}</div>
            </div>
            <p className="fb-text">{msg}</p>
            <div className="meta">
              <span>{date}</span>
              {f.order_id && <span className="fb-oid"> · Order #{f.order_id}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function OffersTab({ offers, refresh, token }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newOffer, setNewOffer] = useState({ title: '', discount: '', description: '', active: true, items: '' });

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${BOT_API}/staff/offers`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newOffer)
      });
      if (res.ok) {
        setShowAdd(false);
        refresh();
      }
    } catch (err) { console.error(err); }
  };

  return (
    <div className="offers-container">
       <button onClick={() => setShowAdd(true)} className="btn-primary" style={{ marginBottom: 20 }}>
          <Plus size={16} /> New Promos
        </button>

        {showAdd && (
          <div className="modal-overlay">
            <form className="staff-modal" onSubmit={handleSave}>
              <h3>Create Offer</h3>
               <div className="form-group"><label>Title</label><input required value={newOffer.title} onChange={e => setNewOffer({...newOffer, title: e.target.value})} /></div>
               <div className="form-group"><label>Description</label><textarea placeholder="e.g. 2 burgers and a large drink" value={newOffer.description} onChange={e => setNewOffer({...newOffer, description: e.target.value})} style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '4px', padding: '8px', width: '100%' }} /></div>
               <div className="form-group"><label>Discount Info</label><input placeholder="e.g. 15% OFF or Rs 500" value={newOffer.discount} onChange={e => setNewOffer({...newOffer, discount: e.target.value})} /></div>
               <div className="form-group"><label>Eligible Items</label><input placeholder="e.g. Burger, Drink" value={newOffer.items} onChange={e => setNewOffer({...newOffer, items: e.target.value})} /></div>
              <div className="modal-actions">
                <button type="button" onClick={() => setShowAdd(false)}>Cancel</button>
                <button type="submit" className="btn-save">Launch Offer</button>
              </div>
            </form>
          </div>
        )}

         <div className="offers-grid">
            {offers.map((offer, i) => (
              <div className={`offer-card ${offer.active ? 'active' : ''}`} key={i}>
                 <h4>{offer.title}</h4>
                 <p className="discount">
                   {offer.discount || (offer.discount_pct ? `${offer.discount_pct}% OFF` : (offer.deal_price ? `Rs ${offer.deal_price}` : 'Special Deal'))}
                 </p>
                 {offer.description && <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', marginBottom: '0.5rem' }}>{offer.description}</p>}
                 {offer.items && (
                   <p className="items">
                     Valid on: {Array.isArray(offer.items) ? offer.items.join(', ') : offer.items}
                   </p>
                 )}
                 <div className={`status-pill ${offer.active ? 'online' : 'offline'}`} style={{ marginTop: 'auto' }}>
                   {offer.active ? 'ACTIVE' : 'INACTIVE'}
                 </div>
              </div>
            ))}
         </div>
    </div>
  );
}

function StaffChat({ token }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setLoading(true);

    try {
      const res = await fetch(`${BOT_API}/staff/chat`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message: msg, history: messages.slice(-5) })
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'bot', content: data.reply }]);
    } catch (err) { console.error(err); }
    setLoading(false);
  };

  return (
    <div className="staff-chat-container">
      {messages.length === 0 && (
        <div className="chat-welcome">
          <h3>Staff AI Copilot</h3>
          <p>Ask about analytics, menu changes, or order strategies.</p>
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
      </div>
      <div className="chat-input-bar">
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} placeholder="Ask AI anything..." />
        <button onClick={handleSend} disabled={loading}>Send</button>
      </div>
    </div>
  );
}
