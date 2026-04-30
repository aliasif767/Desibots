import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Auth from './pages/Auth';
import Sidebar from './components/Sidebar';
import FirstAidBot from './pages/FirstAidBot';
import HisabBot from './pages/HisabBot';
import LawBot from './pages/LawBot';
import PakOrderBot from './pages/PakOrderBot';
import StaffDashboard from './pages/StaffDashboard';
import SehatStaffDashboard from './pages/SehatStaffDashboard';
import Admin from './pages/Admin';

const API_BASE = '/api';

function AppLayout({ children, token, subscribedBots, username, role, handleLogout }) {
  const isSubscribed = role === 'admin' || (subscribedBots && subscribedBots.length > 0);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const isAuthPage = location.pathname === '/auth' || !token;

  if (isAuthPage) {
    return <div className="app-container">{children}</div>;
  }

  return (
    <div className="app-container">
      <Sidebar 
        collapsed={collapsed} 
        setCollapsed={setCollapsed} 
        username={username} 
        isSubscribed={isSubscribed} 
        role={role}
        handleLogout={handleLogout} 
      />
      <div className="main-content">
        {children}
      </div>
    </div>
  );
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  
  const getInitialSubs = () => {
    try {
      const val = localStorage.getItem('subscribedBots');
      if (!val) return [];
      const parsed = JSON.parse(val);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  const [subscribedBots, setSubscribedBots] = useState(getInitialSubs());
  const [username, setUsername] = useState(localStorage.getItem('username'));
  const [role, setRole] = useState(localStorage.getItem('role') || 'user');

  useEffect(() => {
    if (token) {
      fetch(`${API_BASE}/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          handleLogout();
        } else {
          setSubscribedBots(data.subscribedBots || []);
          setUsername(data.username);
          setRole(data.role);
          localStorage.setItem('subscribedBots', JSON.stringify(data.subscribedBots || []));
          localStorage.setItem('role', data.role);
        }
      })
      .catch(() => handleLogout());
    }
  }, [token]);

  const handleLogin = (newToken, subBots, uname, userRole = 'user') => {
    localStorage.setItem('token', newToken);
    localStorage.setItem('subscribedBots', JSON.stringify(subBots));
    localStorage.setItem('username', uname);
    localStorage.setItem('role', userRole);
    setToken(newToken);
    setSubscribedBots(subBots);
    setUsername(uname);
    setRole(userRole);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('subscribedBots');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    setToken(null);
    setSubscribedBots([]);
    setUsername(null);
    setRole('user');
  };

  return (
    <Router>
      <AppLayout token={token} subscribedBots={subscribedBots} username={username} role={role} handleLogout={handleLogout}>
        <Routes>
          <Route path="/" element={token ? <Navigate to="/dashboard" /> : <Navigate to="/auth" />} />
          <Route path="/auth" element={!token ? <Auth onLogin={handleLogin} apiBase={API_BASE} /> : <Navigate to="/dashboard" />} />
          <Route path="/dashboard" element={token ? <Dashboard token={token} subscribedBots={subscribedBots} setSubscribedBots={setSubscribedBots} role={role} apiBase={API_BASE} /> : <Navigate to="/auth" />} />
          <Route path="/admin" element={token && role === 'admin' ? <Admin token={token} apiBase={API_BASE} /> : <Navigate to="/dashboard" />} />
          
          {/* Bot Pages */}
          <Route path="/bot/firstaid" element={token ? <FirstAidBot token={token} /> : <Navigate to="/auth" />} />
          <Route path="/bot/hisabot" element={token ? <HisabBot token={token} /> : <Navigate to="/auth" />} />
          <Route path="/bot/lawbot" element={token ? <LawBot token={token} /> : <Navigate to="/auth" />} />
          <Route path="/bot/pakorder" element={token ? <PakOrderBot token={token} role={role} subscribedBots={subscribedBots} /> : <Navigate to="/auth" />} />
          
          <Route 
            path="/bot/pakorder/staff" 
            element={
              token && (role === 'admin' || subscribedBots.includes('pakorder')) ? 
              <StaffDashboard token={token} /> : 
              <Navigate to="/dashboard" />
            } 
          />
          <Route 
            path="/bot/firstaid/staff" 
            element={
              token && (role === 'admin' || subscribedBots.includes('firstaid')) ? 
              <SehatStaffDashboard token={token} /> : 
              <Navigate to="/dashboard" />
            } 
          />
        </Routes>
      </AppLayout>
    </Router>
  );
}

export default App;
