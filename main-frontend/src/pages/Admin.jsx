import React, { useState, useEffect } from 'react';
import { HeartPulse, Briefcase, Scale, ShoppingCart, ToggleLeft, ToggleRight } from 'lucide-react';

const SYSTEM_BOTS = [
  { id: 'firstaid', name: 'MedAssist AI', icon: <HeartPulse size={24} />, status: 'Active', version: 'v3.2' }, 
  { id: 'hisabot', name: 'Finance Agent', icon: <Briefcase size={24} />, status: 'Active', version: 'v4.0' }, 
  { id: 'lawbot', name: 'Legal Advisor', icon: <Scale size={24} />, status: 'Active', version: 'v2.1' }, 
  { id: 'pakorder', name: 'Logistics AI', icon: <ShoppingCart size={24} />, status: 'Active', version: 'v1.8' } 
];

function Admin({ token, apiBase }) {
  const [metrics, setMetrics] = useState(null);
  const [billingData, setBillingData] = useState([]);
  const [error, setError] = useState('');
  const [allowSignups, setAllowSignups] = useState(true);
  const [maintenanceMode, setMaintenanceMode] = useState(false);

  useEffect(() => {
    fetch(`${apiBase}/admin/metrics`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) setError(data.error);
        else setMetrics(data);
      })
      .catch(err => setError(err.message));

    fetch(`${apiBase}/billing`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setBillingData(data))
      .catch(err => console.error(err));
  }, [apiBase, token]);

  if (error) {
    return <div className="admin-page" style={{ padding: '2rem', color: '#ff4d4f' }}><h2>Error: {error}</h2></div>;
  }

  if (!metrics) {
    return <div className="admin-page" style={{ padding: '2rem', color: '#fff' }}><h2>Loading Admin Data...</h2></div>;
  }

  return (
    <div className="admin-page" style={{ padding: '2rem', color: '#fff', width: '100%', boxSizing: 'border-box' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '2.5rem' }}>Admin Dashboard</h1>
      
      {/* Metrics Row */}
      <div style={{ display: 'flex', gap: '2rem', marginBottom: '2.5rem' }}>
        <div style={{ background: 'rgba(255, 255, 255, 0.05)', padding: '1.5rem', borderRadius: '12px', flex: 1, border: '1px solid rgba(255,255,255,0.1)' }}>
          <h3 style={{ color: '#aaa', margin: 0 }}>Total Registered Users</h3>
          <p style={{ fontSize: '2.4rem', fontWeight: 'bold', margin: '10px 0 0 0', color: '#00d2ff' }}>{metrics.totalUsers}</p>
        </div>
        <div style={{ background: 'rgba(255, 255, 255, 0.05)', padding: '1.5rem', borderRadius: '12px', flex: 1, border: '1px solid rgba(255,255,255,0.1)' }}>
          <h3 style={{ color: '#aaa', margin: 0 }}>Active Pro Subscriptions</h3>
          <p style={{ fontSize: '2.4rem', fontWeight: 'bold', margin: '10px 0 0 0', color: '#f0abfc' }}>{metrics.totalSubscriptions}</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '2rem' }}>
        {/* Token Usage Table */}
        <div style={{ flex: 2, background: 'rgba(255, 255, 255, 0.05)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
          <h3 style={{ margin: '0 0 1rem 0' }}>Bot Token Usage Metrics</h3>
          {metrics.tokenStats && metrics.tokenStats.length > 0 ? (
            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', marginTop: '1rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                  <th style={{ padding: '12px 10px', color: '#aaa' }}>User</th>
                  <th style={{ padding: '12px 10px', color: '#aaa' }}>Bot Service</th>
                  <th style={{ padding: '12px 10px', color: '#aaa', textAlign: 'right' }}>Tokens Used</th>
                </tr>
              </thead>
              <tbody>
                {metrics.tokenStats.map((stat, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '14px 10px', fontWeight: 500 }}>{stat.username}</td>
                    <td style={{ padding: '14px 10px' }}>
                      <span style={{ background: 'rgba(255,255,255,0.1)', padding: '4px 10px', borderRadius: '20px', fontSize: '0.8rem' }}>
                        {stat.botName}
                      </span>
                    </td>
                    <td style={{ padding: '14px 10px', fontWeight: 'bold', color: '#00d2ff', textAlign: 'right', fontSize: '1rem' }}>
                      {stat.tokensUsed.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: '#aaa', marginTop: '1rem' }}>No token usage data yet.</p>
          )}
        </div>

        {/* Right Column: Platform Bots & Settings */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Bots List */}
          <div style={{ background: 'rgba(255, 255, 255, 0.05)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <h3 style={{ margin: '0 0 1.5rem 0' }}>Platform Bots</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {SYSTEM_BOTS.map(bot => (
                <div key={bot.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ color: '#00d2ff' }}>{bot.icon}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{bot.name}</div>
                      <div style={{ fontSize: '0.75rem', color: '#aaa' }}>{bot.version}</div>
                    </div>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#10b981', background: 'rgba(16, 185, 129, 0.1)', padding: '4px 8px', borderRadius: '4px', fontWeight: 'bold' }}>
                    {bot.status}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Platform Settings */}
          <div style={{ background: 'rgba(255, 255, 255, 0.05)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <h3 style={{ margin: '0 0 1.5rem 0' }}>Platform Settings</h3>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.2rem' }}>
              <div>
                <div style={{ fontWeight: 600 }}>Allow New Signups</div>
                <div style={{ fontSize: '0.8rem', color: '#aaa' }}>Open registration for new users</div>
              </div>
              <div style={{ cursor: 'pointer', color: allowSignups ? '#10b981' : '#aaa' }} onClick={() => setAllowSignups(!allowSignups)}>
                {allowSignups ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600 }}>Maintenance Mode</div>
                <div style={{ fontSize: '0.8rem', color: '#aaa' }}>Take bots offline for updates</div>
              </div>
              <div style={{ cursor: 'pointer', color: maintenanceMode ? '#ef4444' : '#aaa' }} onClick={() => setMaintenanceMode(!maintenanceMode)}>
                {maintenanceMode ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Financial Overview */}
      <div style={{ marginTop: '2.5rem', background: 'rgba(255, 255, 255, 0.05)', padding: '2rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
        <h3 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Financial Overview (Pay As You Go)</h3>
        <p style={{ color: '#aaa', marginBottom: '2rem' }}>Rate: 0.05 PKR per token consumed across all bot services.</p>
        
        {billingData && billingData.length > 0 ? (
          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <th style={{ padding: '12px 10px', color: '#aaa' }}>User</th>
                <th style={{ padding: '12px 10px', color: '#aaa' }}>Total Tokens</th>
                <th style={{ padding: '12px 10px', color: '#aaa', textAlign: 'right' }}>Total Bill (PKR)</th>
              </tr>
            </thead>
            <tbody>
              {billingData.map((bill, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '14px 10px', fontWeight: 500 }}>{bill.username}</td>
                  <td style={{ padding: '14px 10px' }}>{bill.totalTokens.toLocaleString()}</td>
                  <td style={{ padding: '14px 10px', fontWeight: 'bold', color: '#10b981', textAlign: 'right', fontSize: '1.2rem' }}>
                    Rs. {bill.bill.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: '#aaa' }}>No billing data generated yet.</p>
        )}
      </div>
    </div>
  );
}

export default Admin;
