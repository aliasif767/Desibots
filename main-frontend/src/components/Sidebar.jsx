import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Users, CreditCard, Settings, LogOut, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';

function Sidebar({ collapsed, setCollapsed, username, isSubscribed, role, handleLogout }) {
  const navigate = useNavigate();

  let navItems = [];

  if (role === 'admin') {
    navItems = [
      { name: 'Admin Dashboard', path: '/admin', icon: <Users size={20} /> }
    ];
  } else {
    navItems = [
      { name: 'Dashboard', path: '/dashboard', icon: <LayoutDashboard size={20} /> },
      { name: 'My Subscriptions', path: '/dashboard?tab=subs', icon: <CreditCard size={20} /> },
     
    ];
  }

  return (
    <motion.div
      className={`sidebar ${collapsed ? 'collapsed' : ''}`}
      initial={{ x: -250 }}
      animate={{ x: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
    >
      <div
        className="sidebar-brand"
        onClick={() => navigate('/dashboard')}
      >
        <div className="sidebar-brand-icon">D</div>
        {!collapsed && <span className="sidebar-brand-text">Desibots</span>}
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item, idx) => (
          <NavLink
            key={idx}
            to={item.path}
            className={({ isActive }) => `nav-item ${isActive && item.path === '/dashboard' ? 'active' : ''}`}
            title={collapsed ? item.name : ''}
          >
            {item.icon}
            {!collapsed && <span className="nav-label">{item.name}</span>}
          </NavLink>
        ))}
      </nav>

      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <button
          onClick={() => setCollapsed(!collapsed)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', padding: '0.5rem', alignSelf: collapsed ? 'center' : 'flex-start' }}
        >
          {collapsed ? <ChevronRight size={20} /> : <><ChevronLeft size={20} /> <span style={{ marginLeft: '0.5rem' }}>Collapse</span></>}
        </button>

        <div className="sidebar-user" onClick={handleLogout} style={{ cursor: 'pointer' }} title={collapsed ? "Logout" : ""}>
          <div className="user-avatar">
            {username ? username.charAt(0).toUpperCase() : 'U'}
          </div>
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'white' }}>{username}</span>
              <span style={{ fontSize: '0.75rem', color: isSubscribed ? '#f0abfc' : 'var(--text-muted)' }}>
                {isSubscribed ? 'Pro Plan' : 'Free Plan'}
              </span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default Sidebar;
