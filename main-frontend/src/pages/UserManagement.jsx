import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, Trash2, ShieldCheck, ShieldAlert, Search, RefreshCw, HeartPulse, Briefcase, Scale, ShoppingCart } from 'lucide-react';

const BOTS = [
  { id: 'firstaid', name: 'Sehat Bot', icon: <HeartPulse size={16} />, color: '#3b82f6' },
  { id: 'hisabot', name: 'Hisab Bot', icon: <Briefcase size={16} />, color: '#10b981' },
  { id: 'lawbot', name: 'Lawyer Bot', icon: <Scale size={16} />, color: '#d946ef' },
  { id: 'pakorder', name: 'PakOrder Bot', icon: <ShoppingCart size={16} />, color: '#f59e0b' }
];

function UserManagement({ token, apiBase }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [updating, setUpdating] = useState(null);

  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/admin/users`, { headers });
      const data = await res.json();
      setUsers(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const deleteUser = async (id) => {
    if (!window.confirm("Are you sure you want to delete this user? All their data will be purged.")) return;
    try {
      const res = await fetch(`${apiBase}/admin/users/${id}`, { method: 'DELETE', headers });
      if (res.ok) fetchUsers();
    } catch (err) {
      console.error(err);
    }
  };

  const toggleSub = async (userId, botId) => {
    setUpdating(`${userId}-${botId}`);
    try {
      const res = await fetch(`${apiBase}/admin/users/${userId}/toggle-subscription`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ botId })
      });
      if (res.ok) fetchUsers();
    } catch (err) {
      console.error(err);
    } finally {
      setUpdating(null);
    }
  };

  const filteredUsers = users.filter(u => u.username.toLowerCase().includes(search.toLowerCase()));

  return (
    <motion.div 
      className="admin-page"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{ padding: '2.5rem', color: '#fff' }}
    >
      <header style={{ marginBottom: '3rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '2.5rem', fontWeight: 800 }}>User <span className="text-gradient">Controller</span></h1>
          <p style={{ color: '#64748b', marginTop: '0.5rem' }}>Manage account access and bot authorizations globally.</p>
        </div>
        <button onClick={fetchUsers} className="btn btn-outline" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <RefreshCw size={18} className={loading ? 'spin' : ''} /> Refresh Data
        </button>
      </header>

      <div style={{ marginBottom: '2rem', position: 'relative' }}>
        <Search style={{ position: 'absolute', left: '1.25rem', top: '50%', transform: 'translateY(-50%)', color: '#64748b' }} size={20} />
        <input 
          type="text" 
          placeholder="Search by username..." 
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: '100%', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '16px', padding: '1rem 1rem 1rem 3.5rem', color: '#fff', fontSize: '1rem' }}
        />
      </div>

      <div style={{ background: 'rgba(255, 255, 255, 0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.06)', overflow: 'hidden' }}>
        {loading && users.length === 0 ? (
           <div style={{ padding: '4rem', textAlign: 'center' }}>
             <div className="loader-ring"><div></div><div></div><div></div><div></div></div>
           </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.03)' }}>
                  <th style={{ padding: '1.5rem', color: '#64748b', fontWeight: 600 }}>User Identity</th>
                  {BOTS.map(bot => (
                    <th key={bot.id} style={{ padding: '1.5rem', color: '#64748b', fontWeight: 600, textAlign: 'center' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.25rem' }}>
                        {bot.icon}
                        <span style={{ fontSize: '0.7rem' }}>{bot.name}</span>
                      </div>
                    </th>
                  ))}
                  <th style={{ padding: '1.5rem', color: '#64748b', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {filteredUsers.map(user => (
                    <motion.tr 
                      key={user._id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                    >
                      <td style={{ padding: '1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                          <div style={{ width: 40, height: 40, background: 'rgba(255,255,255,0.05)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, color: '#00d2ff' }}>
                            {user.username.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div style={{ fontWeight: 700 }}>{user.username}</div>
                            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>ID: {user._id.slice(-8)}</div>
                          </div>
                        </div>
                      </td>
                      {BOTS.map(bot => {
                        const active = user.subscriptions.includes(bot.id);
                        const isUpdating = updating === `${user._id}-${bot.id}`;
                        return (
                          <td key={bot.id} style={{ padding: '1.5rem', textAlign: 'center' }}>
                            <button 
                              onClick={() => toggleSub(user._id, bot.id)}
                              disabled={isUpdating}
                              style={{ 
                                background: active ? `${bot.color}20` : 'rgba(255,255,255,0.03)', 
                                border: '1px solid',
                                borderColor: active ? bot.color : 'rgba(255,255,255,0.08)',
                                color: active ? bot.color : '#64748b',
                                padding: '0.5rem 1rem',
                                borderRadius: '100px',
                                fontSize: '0.75rem',
                                fontWeight: 800,
                                cursor: 'pointer',
                                transition: 'all 0.2s',
                                opacity: isUpdating ? 0.5 : 1
                              }}
                            >
                              {active ? 'AUTHORIZED' : 'LOCKED'}
                            </button>
                          </td>
                        );
                      })}
                      <td style={{ padding: '1.5rem', textAlign: 'right' }}>
                        <button 
                          onClick={() => deleteUser(user._id)}
                          style={{ background: 'rgba(239, 68, 68, 0.1)', border: 'none', color: '#ef4444', padding: '0.75rem', borderRadius: '12px', cursor: 'pointer', transition: 'all 0.2s' }}
                          title="Delete User"
                        >
                          <Trash2 size={18} />
                        </button>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {filteredUsers.length === 0 && !loading && (
              <div style={{ padding: '4rem', textAlign: 'center', color: '#64748b' }}>
                <Users size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                <p>No users found matching your search.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

export default UserManagement;
