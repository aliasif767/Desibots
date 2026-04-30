import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Sparkles } from 'lucide-react';

function Auth({ onLogin, apiBase }) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const endpoint = isLogin ? '/login' : '/signup';
      const res = await fetch(`${apiBase}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.error || 'Authenication failed');
      
      if (isLogin) {
        onLogin(data.token, data.subscribedBots || [], data.username, data.role);
      } else {
        setIsLogin(true);
        setUsername('');
        setPassword('');
        alert('Signup successful! Please log in.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-split-container">
      {/* Visual / Branding Side */}
      <div className="auth-hero">
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)', borderRadius: '30px', marginBottom: '2rem', fontSize: '0.85rem', fontWeight: 600 }}>
            <Sparkles size={16} color="#d946ef" /> 
            <span>Welcome to the future of work</span>
          </div>
          <h1 style={{ fontSize: '4rem', lineHeight: 1.1, marginBottom: '1.5rem', fontWeight: 800 }}>
            Supercharge your workflow with <br />
            <span className="text-gradient">Agentic AI.</span>
          </h1>
          <p style={{ fontSize: '1.2rem', color: 'rgba(255,255,255,0.7)', maxWidth: '500px', lineHeight: 1.6 }}>
            Gain exclusive access to specialized expert agents in medicine, law, finance, and logistics.
          </p>
        </motion.div>
      </div>

      {/* Form Side */}
      <div className="auth-form-wrapper">
        <motion.div 
          className="auth-box"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div style={{ width: 48, height: 48, background: 'linear-gradient(135deg, var(--primary), var(--accent))', borderRadius: 12, margin: '0 auto 2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: 'var(--glow-primary)' }}>
            <span style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>D</span>
          </div>
          
          <h2>{isLogin ? 'Welcome Back' : 'Create an Account'}</h2>
          <p>{isLogin ? 'Enter your credentials to access your agents.' : 'Sign up to start using professional AI tools.'}</p>
          
          {error && (
             <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} style={{ padding: '0.75rem', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.2)', color: '#fba11b', borderRadius: '8px', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                {error}
             </motion.div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="input-group">
              <label>Username</label>
              <input 
                type="text" 
                className="input-field" 
                placeholder="developer123" 
                value={username} 
                onChange={(e) => setUsername(e.target.value)} 
                required 
              />
            </div>
            <div className="input-group">
              <label>Password</label>
              <input 
                type="password" 
                className="input-field" 
                placeholder="••••••••" 
                value={password} 
                onChange={(e) => setPassword(e.target.value)} 
                required 
              />
            </div>
            
            <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: '100%', marginTop: '1rem', padding: '0.85rem' }}>
              {loading ? 'Authenticating...' : isLogin ? 'Sign In' : 'Create Account'}
              {!loading && <ArrowRight size={18} />}
            </button>
          </form>

          <div className="auth-switch">
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <span onClick={() => { setIsLogin(!isLogin); setError(null); }}>
              {isLogin ? 'Sign up' : 'Log in'}
            </span>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

export default Auth;
