import React, { useState, useEffect } from 'react';
import { HeartPulse, Briefcase, Scale, ShoppingCart, ToggleLeft, ToggleRight, Users, CreditCard, Activity, TrendingUp, ShieldAlert, Zap, Server, Globe } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const SYSTEM_BOTS = [
  { id: 'firstaid', name: 'Sehat Bot', icon: <HeartPulse size={22} />, status: 'Active', version: 'v3.2', color: '#3b82f6' }, 
  { id: 'hisabot', name: 'Hisab Bot', icon: <Briefcase size={22} />, status: 'Active', version: 'v4.0', color: '#10b981' }, 
  { id: 'lawbot', name: 'Lawyer Bot', icon: <Scale size={22} />, status: 'Active', version: 'v2.1', color: '#d946ef' }, 
  { id: 'pakorder', name: 'PakOrder Bot', icon: <ShoppingCart size={22} />, status: 'Active', version: 'v1.8', color: '#f59e0b' } 
];

function Admin({ token, apiBase }) {
  const [metrics, setMetrics] = useState(null);
  const [billingData, setBillingData] = useState([]);
  const [settings, setSettings] = useState({ allowSignups: true, maintenanceMode: false });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(null);
  const [activeView, setActiveView] = useState(null); // 'consumption' or 'revenue'

  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [mRes, bRes, sRes] = await Promise.all([
          fetch(`${apiBase}/admin/metrics`, { headers }),
          fetch(`${apiBase}/billing`, { headers }),
          fetch(`${apiBase}/admin/settings`, { headers })
        ]);

        const mData = await mRes.json();
        const bData = await bRes.json();
        const sData = await sRes.json();

        if (mData.error) setError(mData.error);
        else {
          setMetrics(mData);
          setBillingData(bData);
          setSettings(sData);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [apiBase, token]);

  const updateSetting = async (key, value) => {
    setUpdating(key);
    try {
      const res = await fetch(`${apiBase}/admin/settings`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ key, value })
      });
      if (res.ok) {
        setSettings(prev => ({ ...prev, [key]: value }));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setUpdating(null);
    }
  };

  if (error) {
    return (
      <div className="admin-page" style={{ padding: '4rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
        <ShieldAlert size={64} color="#ef4444" style={{ marginBottom: '1.5rem' }} />
        <h2 style={{ color: '#ef4444', fontSize: '2rem' }}>Administrative Error</h2>
        <p style={{ color: '#aaa', maxWidth: '500px', marginTop: '1rem' }}>{error}</p>
        <button onClick={() => window.location.reload()} className="btn btn-outline" style={{ marginTop: '2rem' }}>Retry Connection</button>
      </div>
    );
  }

  if (loading || !metrics) {
    return (
      <div className="admin-page" style={{ padding: '4rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div className="loader-ring"><div></div><div></div><div></div><div></div></div>
        <p style={{ color: '#aaa', marginTop: '1.5rem', letterSpacing: '1px' }}>INITIALIZING COMMAND CENTER...</p>
      </div>
    );
  }

  return (
    <motion.div 
      className="admin-page" 
      initial={{ opacity: 0 }} 
      animate={{ opacity: 1 }}
      style={{ padding: '2.5rem', color: '#fff', width: '100%', boxSizing: 'border-box' }}
    >
      <header style={{ marginBottom: '3rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#00d2ff', marginBottom: '0.5rem', fontWeight: 600, fontSize: '0.9rem', letterSpacing: '1.5px', textTransform: 'uppercase' }}>
            <Activity size={18} /> System Overseer
          </div>
          <h1 style={{ margin: 0, fontSize: '3rem', fontWeight: 800, letterSpacing: '-1px' }}>Platform <span className="text-gradient">Control</span></h1>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '0.5rem 1rem', borderRadius: '100px', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', color: '#10b981', fontSize: '0.85rem', fontWeight: 600 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 10px #10b981' }}></div>
            All Systems Operational
          </div>
          <p style={{ margin: '0.5rem 0 0 0', color: '#64748b', fontSize: '0.85rem' }}>Last heart-beat: Just now</p>
        </div>
      </header>
      
      {/* Metrics Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
        <motion.div 
          whileHover={{ y: -5 }}
          onClick={() => setActiveView('consumption')}
          style={{ cursor: 'pointer', background: activeView === 'consumption' ? 'rgba(0, 210, 255, 0.1)' : 'linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))', padding: '2rem', borderRadius: '24px', border: activeView === 'consumption' ? '1px solid #00d2ff' : '1px solid rgba(255,255,255,0.08)', position: 'relative', overflow: 'hidden' }}
        >
          <div style={{ position: 'absolute', top: '-10px', right: '-10px', opacity: 0.05 }}><Activity size={120} /></div>
          <h3 style={{ color: '#94a3b8', margin: 0, fontSize: '0.9rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px' }}>Resource Consumption</h3>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginTop: '1rem' }}>
            <p style={{ fontSize: '3rem', fontWeight: 800, margin: 0, color: '#00d2ff', lineHeight: 1 }}>Telemetric</p>
          </div>
          <p style={{ marginTop: '1rem', color: '#64748b', fontSize: '0.8rem' }}>Click to view user usage breakdown</p>
        </motion.div>

        <motion.div 
          whileHover={{ y: -5 }}
          onClick={() => setActiveView('revenue')}
          style={{ cursor: 'pointer', background: activeView === 'revenue' ? 'rgba(16, 185, 129, 0.1)' : 'linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))', padding: '2rem', borderRadius: '24px', border: activeView === 'revenue' ? '1px solid #10b981' : '1px solid rgba(255,255,255,0.08)', position: 'relative', overflow: 'hidden' }}
        >
          <div style={{ position: 'absolute', top: '-10px', right: '-10px', opacity: 0.05 }}><TrendingUp size={120} /></div>
          <h3 style={{ color: '#94a3b8', margin: 0, fontSize: '0.9rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px' }}>Revenue Analytics</h3>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginTop: '1rem' }}>
            <p style={{ fontSize: '3rem', fontWeight: 800, margin: 0, color: '#10b981', lineHeight: 1 }}>Financial</p>
          </div>
          <p style={{ marginTop: '1rem', color: '#64748b', fontSize: '0.8rem' }}>Click to view settlement metrics</p>
        </motion.div>

        <motion.div 
          whileHover={{ y: -5 }}
          style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))', padding: '2rem', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.08)', position: 'relative', overflow: 'hidden' }}
        >
          <div style={{ position: 'absolute', top: '-10px', right: '-10px', opacity: 0.05 }}><Server size={120} /></div>
          <h3 style={{ color: '#94a3b8', margin: 0, fontSize: '0.9rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px' }}>System Scale</h3>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginTop: '1rem' }}>
            <p style={{ fontSize: '3.5rem', fontWeight: 800, margin: 0, color: '#f59e0b', lineHeight: 1 }}>{metrics.totalUsers}</p>
            <span style={{ color: '#64748b', fontSize: '1rem' }}>Active Users</span>
          </div>
        </motion.div>
      </div>

      <AnimatePresence mode="wait">
        {activeView === 'consumption' && (
          <motion.section 
            key="consumption"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden', background: 'rgba(255, 255, 255, 0.03)', padding: '2.5rem', borderRadius: '32px', border: '1px solid rgba(255,255,255,0.06)', marginBottom: '3rem' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}><Activity size={24} color="#00d2ff" /> Telemetry Data</h3>
              <button onClick={() => setActiveView(null)} style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer' }}>Close Panel</button>
            </div>
            {metrics.tokenStats && metrics.tokenStats.length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'separate', borderSpacing: '0 0.75rem' }}>
                  <thead>
                    <tr>
                      <th style={{ padding: '0 1rem 1rem 1rem', color: '#64748b', fontSize: '0.85rem' }}>User Identity</th>
                      <th style={{ padding: '0 1rem 1rem 1rem', color: '#64748b', fontSize: '0.85rem' }}>Bot Instance</th>
                      <th style={{ padding: '0 1rem 1rem 1rem', color: '#64748b', fontSize: '0.85rem', textAlign: 'right' }}>Volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.tokenStats.map((stat, idx) => (
                      <tr key={idx} style={{ background: 'rgba(255,255,255,0.02)' }}>
                        <td style={{ padding: '1rem', borderRadius: '16px 0 0 16px', fontWeight: 600 }}>{stat.username}</td>
                        <td style={{ padding: '1rem' }}>
                          <span style={{ background: 'rgba(255,255,255,0.05)', padding: '4px 12px', borderRadius: '100px', fontSize: '0.75rem', color: '#00d2ff' }}>{stat.botName}</span>
                        </td>
                        <td style={{ padding: '1rem', borderRadius: '0 16px 16px 0', fontWeight: 800, color: '#f0abfc', textAlign: 'right' }}>{stat.tokensUsed.toLocaleString()} tkns</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p style={{ textAlign: 'center', color: '#64748b' }}>No telemetry data recorded.</p>}
          </motion.section>
        )}

        {activeView === 'revenue' && (
          <motion.section 
            key="revenue"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.05), transparent)', padding: '3rem', borderRadius: '40px', border: '1px solid rgba(16, 185, 129, 0.1)', marginBottom: '3rem' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 800 }}>Revenue <span className="text-gradient">Settlement</span></h3>
              <button onClick={() => setActiveView(null)} style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer' }}>Close Panel</button>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '2rem' }}>
               <p style={{ color: '#64748b', margin: 0 }}>Projected earnings calculated at <span style={{ color: '#10b981', fontWeight: 700 }}>0.05 PKR</span> / token</p>
               <div style={{ fontSize: '2.5rem', fontWeight: 800, color: '#10b981' }}>
                 Rs. {(billingData?.reduce((acc, curr) => acc + curr.bill, 0) || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
               </div>
            </div>
            {billingData && billingData.length > 0 ? (
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'separate', borderSpacing: '0 0.5rem' }}>
                <tbody>
                  {billingData.map((bill, idx) => (
                    <tr key={idx} style={{ background: 'rgba(255,255,255,0.03)' }}>
                      <td style={{ padding: '1.25rem 1rem', borderRadius: '20px 0 0 20px', fontWeight: 700 }}>{bill.username}</td>
                      <td style={{ padding: '1.25rem 1rem', color: '#94a3b8' }}>{bill.totalTokens.toLocaleString()} tkns</td>
                      <td style={{ padding: '1.25rem 1rem', borderRadius: '0 20px 20px 0', fontWeight: 800, color: '#10b981', textAlign: 'right', fontSize: '1.2rem' }}>
                        Rs. {bill.bill.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p style={{ textAlign: 'center', color: '#64748b' }}>No financial transactions.</p>}
          </motion.section>
        )}
      </AnimatePresence>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2.5rem' }}>
        {/* Right Column: Platform Bots & Settings */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Bots Status Card */}
          <section style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '2.5rem', borderRadius: '32px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 style={{ margin: '0 0 2rem 0', fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}><Globe size={24} color="#f59e0b" /> Engine Status & Maintenance</h3>
            <div style={{ display: 'grid', gap: '1rem' }}>
              {SYSTEM_BOTS.map(bot => {
                const isBotDown = settings[`maintenance_${bot.id}`] || settings.maintenanceMode;
                return (
                  <div key={bot.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1.25rem', background: 'rgba(0,0,0,0.2)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <div style={{ background: `${bot.color}15`, color: bot.color, padding: '0.75rem', borderRadius: '14px' }}>{bot.icon}</div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '1rem' }}>{bot.name}</div>
                        <div style={{ fontSize: '0.8rem', color: isBotDown ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                          {isBotDown ? 'Under Maintenance' : 'Operational'}
                        </div>
                      </div>
                    </div>
                    <div 
                      style={{ cursor: updating === `maintenance_${bot.id}` ? 'wait' : 'pointer', opacity: updating === `maintenance_${bot.id}` ? 0.5 : 1, color: isBotDown ? '#ef4444' : '#64748b' }} 
                      onClick={() => !updating && updateSetting(`maintenance_${bot.id}`, !settings[`maintenance_${bot.id}`])}
                    >
                      {isBotDown ? <ToggleRight size={38} /> : <ToggleLeft size={38} />}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Platform Configuration Card */}
          <section style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '2.5rem', borderRadius: '32px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 style={{ margin: '0 0 2rem 0', fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}><Server size={24} color="#d946ef" /> Global Parameters</h3>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', background: 'rgba(255,255,255,0.02)', padding: '1.5rem', borderRadius: '20px' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '1.05rem' }}>Allow New Signups</div>
                <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '0.25rem' }}>Public user registration access</div>
              </div>
              <div 
                style={{ cursor: updating === 'allowSignups' ? 'wait' : 'pointer', opacity: updating === 'allowSignups' ? 0.5 : 1, color: settings.allowSignups ? '#10b981' : '#64748b' }} 
                onClick={() => !updating && updateSetting('allowSignups', !settings.allowSignups)}
              >
                {settings.allowSignups ? <ToggleRight size={48} /> : <ToggleLeft size={48} />}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '1.5rem', borderRadius: '20px' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#ef4444' }}>Global Maintenance</div>
                <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '0.25rem' }}>Force all bots offline immediately</div>
              </div>
              <div 
                style={{ cursor: updating === 'maintenanceMode' ? 'wait' : 'pointer', opacity: updating === 'maintenanceMode' ? 0.5 : 1, color: settings.maintenanceMode ? '#ef4444' : '#64748b' }} 
                onClick={() => !updating && updateSetting('maintenanceMode', !settings.maintenanceMode)}
              >
                {settings.maintenanceMode ? <ToggleRight size={48} /> : <ToggleLeft size={48} />}
              </div>
            </div>
          </section>

        </div>
      </div>

      {/* Dynamic Growth Indicator */}
      <div style={{ marginTop: '4rem', textAlign: 'center', opacity: 0.3 }}>
        <div style={{ fontSize: '0.75rem', letterSpacing: '4px', textTransform: 'uppercase', marginBottom: '1rem' }}>Infrastructure Scalability Matrix</div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem' }}>
          {Array.from({ length: Math.min(20, metrics.totalUsers + metrics.totalSubscriptions) }).map((_, i) => (
            <div key={i} style={{ width: 4, height: 16 + Math.random() * 20, background: '#00d2ff', borderRadius: '2px' }}></div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

export default Admin;
