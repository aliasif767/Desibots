import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HeartPulse, Briefcase, Scale, ShoppingCart, Lock, ArrowRight, ShieldCheck, Zap, CreditCard as CardIcon, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const BOTS = [
  { id: 'firstaid', name: 'Sehat Bot', icon: <HeartPulse size={28} />, description: 'AI-powered immediate medical guidance and triage assessment.', color: '#3b82f6' }, // Blue
  { id: 'hisabot', name: 'Hisab Bot', icon: <Briefcase size={28} />, description: 'Professional financial auditing and ledger analysis tools.', color: '#10b981' }, // Emerald
  { id: 'lawbot', name: 'Lawyer Bot', icon: <Scale size={28} />, description: 'Instant legal guidance using comprehensive document retrieval.', color: '#d946ef' }, // Fuchsia
  { id: 'pakorder', name: 'Pakorder Bot', icon: <ShoppingCart size={28} />, description: 'Automated logistics and ordering system intelligence.', color: '#f59e0b' } // Amber
];

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.15 }
  }
};

const itemVariants = {
  hidden: { y: 30, opacity: 0 },
  show: { y: 0, opacity: 1, transition: { type: 'spring', stiffness: 100 } }
};

function Dashboard({ token, subscribedBots, setSubscribedBots, role, apiBase }) {
  const navigate = useNavigate();
  const location = useLocation();
  const query = new URLSearchParams(location.search);
  const tab = query.get('tab');

  const [showPayment, setShowPayment] = useState(false);
  const [selectedBot, setSelectedBot] = useState(null);

  // Payment states
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvv, setCvv] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [billing, setBilling] = useState(null);

  React.useEffect(() => {
    fetch(`${apiBase}/billing`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setBilling(data))
      .catch(err => console.error(err));
  }, [apiBase, token]);

  const isAdmin = role === 'admin';
  const isBotSubscribed = (botId) => isAdmin || (subscribedBots && subscribedBots.includes(botId));

  const filteredBots = tab === 'subs'
    ? BOTS.filter(bot => subscribedBots.includes(bot.id))
    : BOTS;

  const handleBotClick = (botId) => {
    if (isBotSubscribed(botId)) {
      navigate(`/bot/${botId}`);
    } else {
      setSelectedBot(botId);
      setShowPayment(true);
    }
  };

  const handleSubscribe = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ botId: selectedBot, cardNumber, expiry, cvv, name, email })
      });
      if (res.ok) {
        const newSubscribed = [...subscribedBots, selectedBot];
        setSubscribedBots(newSubscribed);
        localStorage.setItem('subscribedBots', JSON.stringify(newSubscribed));
        setShowPayment(false);
        if (selectedBot) {
          navigate(`/bot/${selectedBot}`);
        }
      } else {
        alert("Payment failed");
      }
    } catch (err) {
      alert("Error processing payment");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dashboard-content">
      <motion.div
        className="dashboard-hero"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        <span className="premium-badge"><Zap size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} /> Professional AI Suite</span>
        <h1>{tab === 'subs' ? 'My ' : 'Select your '}<span className="text-gradient">AI Specialist{tab === 'subs' ? 's' : ''}</span></h1>
        <p>{tab === 'subs' ? 'The expert agents you have authorized for immediate assistance.' : 'Expertly trained agents waiting to assist you with precision and speed.'}</p>
      </motion.div>

      <motion.div
        className="bots-grid"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {filteredBots.length > 0 ? filteredBots.map(bot => {
          const subscribed = isBotSubscribed(bot.id);
          return (
            <motion.div
              key={bot.id}
              variants={itemVariants}
              className="bot-card"
              onClick={() => handleBotClick(bot.id)}
            >
              <div className="bot-card-border" style={{ background: `linear-gradient(135deg, ${bot.color}44, transparent 50%)` }}></div>
              <div className="bot-icon-wrapper" style={{ color: bot.color }}>
                <div style={{ background: bot.color, position: 'absolute', inset: 0, opacity: 0.15 }}></div>
                {bot.icon}
              </div>
              <h3>{bot.name}</h3>
              <p>{bot.description}</p>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: subscribed ? bot.color : 'var(--text-muted)', fontWeight: 600, fontSize: '0.9rem', marginTop: 'auto' }}>
                {subscribed ? (
                  <><span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><ShieldCheck size={16} /> Authorized</span> <ArrowRight size={18} /></>
                ) : (
                  <><span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Lock size={16} /> Upgrade Required</span> <ArrowRight size={18} /></>
                )}
              </div>
            </motion.div>
          );
        }) : (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '4rem', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px dashed rgba(255,255,255,0.1)' }}>
            <div style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}><Search size={48} style={{ margin: '0 auto' }} /></div>
            <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>No active subscriptions</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>You haven't subscribed to any AI agents yet. Explore the gallery to find the right specialist for your needs.</p>
            <button className="btn btn-accent" onClick={() => navigate('/dashboard')}>Browse All Bots</button>
          </div>
        )}
      </motion.div>

      {/* Usage & Billing Section */}
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        style={{ marginTop: '4rem', background: 'rgba(255, 255, 255, 0.03)', padding: '2.5rem', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.06)' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '2rem' }}>
          <div>
            <h2 style={{ fontSize: '1.75rem', marginBottom: '0.5rem' }}>Usage & <span className="text-gradient">Billing</span></h2>
            <p style={{ color: 'var(--text-muted)' }}>Real-time pay-as-you-go metrics at 0.05 PKR per token.</p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Current Balance Due</div>
            <div style={{ fontSize: '2.2rem', fontWeight: 800, color: '#10b981' }}>
              Rs. {billing?.totalBill?.toLocaleString(undefined, { minimumFractionDigits: 2 }) || '0.00'}
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
          {billing?.breakdown?.length > 0 ? billing.breakdown.map((item, idx) => (
            <div key={idx} style={{ background: 'rgba(255,255,255,0.03)', padding: '1.25rem', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '0.5rem' }}>{item._id}</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.25rem' }}>{item.tokens.toLocaleString()} <span style={{fontSize:'0.8rem', color:'var(--text-muted)'}}>tokens</span></div>
              <div style={{ color: '#10b981', fontWeight: 600 }}>Rs. {item.cost.toLocaleString()}</div>
            </div>
          )) : (
            <div style={{ gridColumn: '1 / -1', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No usage recorded for this billing cycle.
            </div>
          )}
        </div>
      </motion.div>

      <AnimatePresence>
        {showPayment && (
          <motion.div
            className="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="modal-content"
              initial={{ scale: 0.95, y: 20, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.95, y: 20, opacity: 0 }}
            >
              <button className="close-btn" onClick={() => setShowPayment(false)}>&times;</button>

              <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
                <div style={{ width: 64, height: 64, background: 'rgba(217, 70, 239, 0.1)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem', color: '#d946ef', boxShadow: '0 0 30px rgba(217, 70, 239, 0.2)' }}>
                  <CardIcon size={32} />
                </div>
                <h2 style={{ fontSize: '1.75rem', marginBottom: '0.5rem' }}>Upgrade to <span className="text-gradient">Pro</span></h2>
                <p style={{ color: 'var(--text-muted)' }}>Get unlimited access to all expert AI agents.</p>
              </div>

              <form onSubmit={handleSubscribe}>
                <div className="input-group">
                  <label>Name on Card</label>
                  <input required type="text" className="input-field" placeholder="John Doe" value={name} onChange={e => setName(e.target.value)} />
                </div>
                <div className="input-group">
                  <label>Confirmation Email</label>
                  <input required type="email" className="input-field" placeholder="your@email.com" value={email} onChange={e => setEmail(e.target.value)} />
                </div>
                <div className="input-group">
                  <label>Card Number</label>
                  <input required type="text" className="input-field" placeholder="0000 0000 0000 0000" maxLength="16" value={cardNumber} onChange={e => setCardNumber(e.target.value)} />
                </div>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <div className="input-group" style={{ flex: 1 }}>
                    <label>Expiry</label>
                    <input required type="text" className="input-field" placeholder="MM/YY" maxLength="5" value={expiry} onChange={e => setExpiry(e.target.value)} />
                  </div>
                  <div className="input-group" style={{ flex: 1 }}>
                    <label>CVV</label>
                    <input required type="password" className="input-field" placeholder="123" maxLength="4" value={cvv} onChange={e => setCvv(e.target.value)} />
                  </div>
                </div>
                <button disabled={loading} type="submit" className="btn btn-accent" style={{ width: '100%', marginTop: '1.5rem', padding: '1rem', fontSize: '1.05rem' }}>
                  {loading ? 'Processing Secure Payment...' : 'Subscribe Now — $49/mo'}
                </button>
                <div style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}>
                  <ShieldCheck size={14} /> Secured by AES-256 Encryption
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default Dashboard;
