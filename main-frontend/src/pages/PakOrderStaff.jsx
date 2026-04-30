import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { motion } from 'framer-motion';

export default function PakOrderStaff({ token }) {
  const navigate = useNavigate();
  // We point to the proxied Streamlit UI /Staff_panel page
  const STREAMLIT_URL = `/api/bot/pakorder-ui/Staff_panel?token=${token}`;

  return (
    <motion.div 
      className="bot-page" 
      initial={{ opacity: 0 }} 
      animate={{ opacity: 1 }} 
      transition={{ duration: 0.3 }}
      style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}
    >
      <div className="bot-topbar">
        <div className="bot-topbar-left">
          <button 
            className="btn btn-outline" 
            onClick={() => navigate('/bot/pakorder')} 
            style={{ padding: '0.4rem 0.8rem', borderRadius: 8 }}
          >
            <ArrowLeft size={16}/> Back to Chat
          </button>
          <div className="bot-status-dot" style={{ background: '#f59e0b', boxShadow: '0 0 10px #f59e0b' }} />
          <span style={{ fontWeight: 600, fontSize: '1.05rem' }}>👨‍🍳 Restaurant Staff Panel</span>
        </div>
        <a 
          href={STREAMLIT_URL} 
          target="_blank" 
          rel="noopener noreferrer"
          className="btn btn-outline"
          style={{ borderRadius: 10, fontSize: '0.82rem', borderColor: 'rgba(245,158,11,0.3)', color: '#fbbf24', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <ExternalLink size={14}/> Open in New Tab
        </a>
      </div>

      <div style={{ flex: 1, position: 'relative', background: '#08090f' }}>
        <iframe 
          src={STREAMLIT_URL} 
          style={{ 
            width: '100%', 
            height: '100%', 
            border: 'none',
            background: '#08090f'
          }}
          title="PakOrderBot Staff Panel"
        />
      </div>
    </motion.div>
  );
}
