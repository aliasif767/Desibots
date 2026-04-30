require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { spawn } = require('child_process');
const path = require('path');
const nodemailer = require('nodemailer');
const axios = require('axios');
const crypto = require('crypto');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const { createProxyMiddleware, responseInterceptor } = require('http-proxy-middleware');
const { setupDB, User, Subscription, TokenUsage } = require('./db.js');
const mongoose = require('mongoose');
const cookieParser = require('cookie-parser');

const app = express();
const PORT = process.env.PORT || 8000;
const JWT_SECRET = process.env.JWT_SECRET || 'supersecretkey123';

const BOT_API_URLS = {
  firstaid: process.env.FIRSTAID_API_URL || 'http://127.0.0.1:8510',
  hisabot:  process.env.HISABOT_API_URL  || 'http://127.0.0.1:8511',
  lawbot:   process.env.LAWBOT_API_URL   || 'http://127.0.0.1:8513',
  pakorder: process.env.PAKORDER_API_URL || 'http://127.0.0.1:8512',
  'pakorder-ui': 'http://127.0.0.1:8501',
};

app.use(cors({ origin: '*' }));
app.use(cookieParser());

setupDB().then(() => {
  console.log('Main Backend MongoDB initialized.');
}).catch(console.error);

const authenticateToken = (req, res, next) => {
  let token = req.header('Authorization')?.split(' ')[1] || req.query.token || req.cookies?.proxy_token;
  if (!token) return res.status(401).json({ error: 'Access Denied' });
  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.status(403).json({ error: 'Invalid Token' });
    req.user = user;
    
    // If token came from query string (initial load), persist it in a cookie for sub-requests (JS/CSS/WS)
    if (req.query.token) {
      res.cookie('proxy_token', req.query.token, {
        httpOnly: true,
        secure: false, // Set to true in production with HTTPS
        sameSite: 'lax',
        maxAge: 24 * 60 * 60 * 1000 // 24 hours
      });
    }
    next();
  });
};

const requireBotSubscription = (botId) => async (req, res, next) => {
  if (req.user && req.user.role === 'admin') return next();
  try {
    const sub = await Subscription.findOne({ userId: req.user.id, botId, active: true });
    if (!sub) return res.status(403).json({ error: `Subscription for ${botId} required.` });
    next();
  } catch {
    res.status(500).json({ error: 'Database error' });
  }
};

const requireAdmin = async (req, res, next) => {
  if (req.user && req.user.role === 'admin') return next();
  res.status(403).json({ error: 'Admin Access Required' });
};

// ──────────────────────────────────────────────────────────────────
// BOT API PROXY
const makeBotApiProxy = (botKey) => {
  const target = BOT_API_URLS[botKey];
  return createProxyMiddleware({
    target,
    changeOrigin: true,
    selfHandleResponse: true, // required for responseInterceptor
    pathRewrite: (path) => {
      return path.replace(`/api/bot/${botKey}`, '') || '/';
    },
    on: {
      proxyReq: async (proxyReq, req, res) => {
        // Inject auth tenant headers needed by the bot
        if (req.user) {
          const tenantId = req.user.username;
          proxyReq.setHeader('x-tenant-id', tenantId);
          proxyReq.setHeader('x-tenant-username', req.user.username);
          
          // Ensure role is present
          let role = req.user.role || 'user';
          
          // CRITICAL: If a user has a subscription (verified by previous middleware), 
          // they are the "Staff/Owner" of their own bot instance.
          if (role === 'user') {
            role = 'staff';
          }
          
          proxyReq.setHeader('x-tenant-role', role);
          console.log(`[Proxy][${botKey}] Elevating to: ${role} for tenant: ${req.user.username}`);
        }
        
        // Fix body parsing being swallowed by express.json if it was mounted before
        // Here we didn't mount express.json() yet globally, but just in case:
        if (req.body && Object.keys(req.body).length > 0) {
            const bodyData = JSON.stringify(req.body);
            proxyReq.setHeader('Content-Type', 'application/json');
            proxyReq.setHeader('Content-Length', Buffer.byteLength(bodyData));
            proxyReq.write(bodyData);
        }
      },
      proxyRes: responseInterceptor(async (responseBuffer, proxyRes, req, res) => {
        // Log token usage async
        if (req.user && responseBuffer) {
           try {
             // Basic parsing check—won't intercept if response is binary (e.g. streaming chunks may fail toString if not text)
             const reqString = req.body ? JSON.stringify(req.body) : '';
             const resString = responseBuffer.toString('utf8');
             
             // Rough heuristic: 4 chars per token.
             const reqTokens = Math.ceil(reqString.length / 4);
             const resTokens = Math.ceil(resString.length / 4);
             const totalTokens = reqTokens + resTokens;

             if (totalTokens > 0) {
               TokenUsage.create({
                   userId: req.user.id,
                   botName: botKey,
                   tokensUsed: totalTokens
               }).catch(err => console.error("TokenUsage save err:", err));
             }
           } catch (e) {
             console.error("Token tracking parsing error", e);
           }
        }
        return responseBuffer;
      }),
      error: (err, req, res) => {
        console.error(`[BotProxy][${botKey}] Error:`, err.message);
        if (res && typeof res.status === 'function' && !res.headersSent) {
          res.status(502).json({ error: `Bot service "${botKey}" is offline. Please start it first.` });
        }
      }
    }
  });
};

// ──────────────────────────────────────────────────────────────────
// WEBHOOK PROXIES (No Auth)
app.use('/api/webhook/twilio', createProxyMiddleware({
  target: BOT_API_URLS['pakorder'],
  changeOrigin: true,
  pathRewrite: (path) => '/whatsapp'
}));

app.use('/api/webhook/hisabot', createProxyMiddleware({
  target: BOT_API_URLS['hisabot'],
  changeOrigin: true,
  pathRewrite: (path) => '/whatsapp/webhook'
}));

// Direct /whatsapp route for easier ngrok/Twilio configuration
app.use('/whatsapp', createProxyMiddleware({
  target: BOT_API_URLS['hisabot'],
  changeOrigin: true,
  pathRewrite: (path) => '/wa'
}));


Object.keys(BOT_API_URLS).forEach(botKey => {
  const isUI = botKey.endsWith('-ui');
  app.use(
    `/api/bot/${botKey}`,
    authenticateToken,
    requireBotSubscription(isUI ? botKey.replace('-ui','') : botKey),
    isUI ? createProxyMiddleware({
      target: BOT_API_URLS[botKey],
      changeOrigin: true,
      ws: true,
      pathRewrite: (path, req) => req.originalUrl.split('?')[0], // Preserve full path for Streamlit baseUrlPath
      on: {
        error: (err, req, res) => {
          console.error(`[UIProxy][${botKey}] Error:`, err.message);
          if (res && !res.headersSent) res.status(502).json({ error: "UI Service Offline" });
        }
      }
    }) : makeBotApiProxy(botKey)
  );
});

// ──────────────────────────────────────────────────────────────────
// INTERNAL API ROUTES
const apiRouter = express.Router();
// Mount body parser ONLY for internal API routes so it doesn't break Proxy payload
apiRouter.use(express.json());

apiRouter.post('/signup', async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password)
    return res.status(400).json({ error: 'Username and password required' });
  try {
    const hashed = await bcrypt.hash(password, 10);
    await User.create({ username, password: hashed });
    res.status(201).json({ message: 'User created' });
  } catch {
    res.status(400).json({ error: 'User may already exist' });
  }
});

apiRouter.post('/login', async (req, res) => {
  const { username, password } = req.body;
  try {
    const user = await User.findOne({ username });
    if (!user || !(await bcrypt.compare(password, user.password)))
      return res.status(400).json({ error: 'Invalid credentials' });
    const token = jwt.sign({ id: user._id, username: user.username, role: user.role }, JWT_SECRET, { expiresIn: '24h' });
    const subs = await Subscription.find({ userId: user._id, active: true });
    const subscribedBots = subs.map(s => s.botId);
    res.json({ token, subscribedBots, username: user.username, role: user.role });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
});

apiRouter.get('/me', authenticateToken, async (req, res) => {
  try {
    const subs = await Subscription.find({ userId: req.user.id, active: true });
    const subscribedBots = subs.map(s => s.botId);
    res.json({ username: req.user.username, subscribedBots, role: req.user.role });
  } catch {
    res.status(500).json({ error: 'Server error' });
  }
});

// Email Transporter Configuration
let transporter;
const setupTransporter = async () => {
  if (process.env.SMTP_USER && process.env.SMTP_PASS) {
    // Use real SMTP if provided
    transporter = nodemailer.createTransport({
      host: process.env.SMTP_HOST || 'smtp.gmail.com',
      port: process.env.SMTP_PORT || 587,
      secure: process.env.SMTP_SECURE === 'true',
      auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS
      },
      family: 4 // Force IPv4 to avoid ENETUNREACH issues
    });
    console.log('Using Real SMTP Transporter');
  } else {
    // Fallback to Ethereal for testing
    try {
      const testAccount = await nodemailer.createTestAccount();
      transporter = nodemailer.createTransport({
        host: 'smtp.ethereal.email',
        port: 587,
        secure: false,
        auth: {
          user: testAccount.user,
          pass: testAccount.pass
        }
      });
      console.log('Using Ethereal Test Transporter');
      console.log('----------------------------------------------------');
      console.log(`Test Email Account: ${testAccount.user}`);
      console.log(`Test Email Pass: ${testAccount.pass}`);
      console.log('----------------------------------------------------');
    } catch (err) {
      console.error('Failed to create Ethereal test account:', err.message);
    }
  }
};
setupTransporter();

apiRouter.post('/subscribe', authenticateToken, async (req, res) => {
  const { botId, cardNumber, expiry, cvv, name, email } = req.body;
  if (!botId || !cardNumber || !expiry || !cvv || !name || !email)
    return res.status(400).json({ error: 'Missing details' });

  try {
    // 1. Generate staff credentials for specific bots
    let staffPassword = '';
    const needsStaff = ['pakorder', 'firstaid'].includes(botId);
    
    if (needsStaff) {
      staffPassword = crypto.randomBytes(4).toString('hex'); // 8 char random hex
    }

    // 2. Save/Update Subscription
    let subscription = await Subscription.findOne({ userId: req.user.id, botId });
    if (subscription) {
      subscription.active = true;
      subscription.email = email;
      if (needsStaff) subscription.staffPassword = staffPassword;
      await subscription.save();
    } else {
      subscription = await Subscription.create({ 
        userId: req.user.id, 
        botId, 
        email, 
        active: true,
        staffPassword: needsStaff ? staffPassword : null
      });
    }

    // 3. Trigger Bot Staff Seeding
    const botUrls = {
      'pakorder': process.env.PAKORDER_API_URL || 'http://127.0.0.1:8512',
      'firstaid': process.env.FIRSTAID_API_URL || 'http://127.0.0.1:8510'
    };

    if (needsStaff && botUrls[botId]) {
      const seedPath = botId === 'firstaid' ? '/staff/seed-staff' : '/seed-staff';
      try {
        await axios.post(`${botUrls[botId]}${seedPath}`, {
          username: req.user.username,
          password: staffPassword
        }, {
          headers: { 'x-tenant-id': req.user.username }
        });
      } catch (err) {
        console.error(`Failed to seed staff for ${botId}:`, err.message);
        // Continue anyway, maybe it already exists or bot is down
      }
    }

    // 4. Create Rich HTML Email Template
    const botName = botId === 'hisabot' ? 'HisabBot' : 
                   botId === 'firstaid' ? 'SehatBot' : 
                   botId === 'pakorder' ? 'PakOrderBot' : 'LawBot';
    
    const botColor = botId === 'firstaid' ? '#3b82f6' : 
                    botId === 'pakorder' ? '#f59e0b' : 
                    botId === 'hisabot' ? '#10b981' : '#d946ef';

    const htmlContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7fa; margin: 0; padding: 0; }
        .container { max-width: 600px; margin: 20px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .header { background: linear-gradient(135deg, ${botColor}, #1e293b); padding: 40px 20px; text-align: center; color: #ffffff; }
        .header h1 { margin: 0; font-size: 28px; letter-spacing: 1px; }
        .content { padding: 30px; color: #334155; line-height: 1.6; }
        .welcome { font-size: 20px; font-weight: 600; margin-bottom: 10px; color: #1e293b; }
        .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 25px 0; }
        .card-title { font-weight: 700; color: ${botColor}; margin-bottom: 15px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; text-transform: uppercase; font-size: 13px; }
        .credential-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 15px; }
        .label { color: #64748b; font-weight: 500; }
        .value { color: #1e293b; font-weight: 600; font-family: monospace; }
        .btn { display: inline-block; background: ${botColor}; color: #ffffff !important; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9; }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>Desibots Hub</h1>
          <p>Your AI Specialist is Ready</p>
        </div>
        <div class="content">
          <div class="welcome">Hello, ${name}!</div>
          <p>Congratulations! Your subscription to <strong>${botName}</strong> is now active. You have successfully unlocked professional-grade AI intelligence tailored for your needs.</p>
          
          ${needsStaff ? `
          <div class="card">
            <div class="card-title">Staff Side Panel Credentials</div>
            <div class="credential-row"><span class="label">Tenant ID:</span> <span class="value">${req.user.username}</span></div>
            <div class="credential-row"><span class="label">Username:</span> <span class="value">${req.user.username}</span></div>
            <div class="credential-row"><span class="label">Password:</span> <span class="value">${staffPassword}</span></div>
          </div>
          <p style="font-size: 14px; color: #64748b;">Use these credentials to access your hospital/kitchen management portal directly from the dashboard.</p>
          ` : ''}

          <center>
            <a href="http://localhost:5173/dashboard" class="btn">Launch ${botName} Workspace</a>
          </center>
        </div>
        <div class="footer">
          &copy; 2026 Desibots Advanced Coding Team. All rights reserved.<br>
          This is an automated notification. Please do not reply.
        </div>
      </div>
    </body>
    </html>
    `;

    let plainText = `Dear ${name},\n\nThank you for subscribing to ${botName}!\nYour subscription is now active.`;
    if (needsStaff) {
      plainText += `\n\nYour Staff Credentials:\nTenant ID: ${req.user.username}\nUsername: ${req.user.username}\nPassword: ${staffPassword}`;
    }

    plainText += `\n\nBest regards,\nDesibots Team`;

    // In a real app, you'd use transporter.sendMail
    console.log(`[EMAIL SENT TO ${email}]:\n${plainText}`);
    
    // Attempt real send
    if (transporter) {
      transporter.sendMail({
        from: `"Desibots Hub" <${process.env.SMTP_USER || 'noreply@desibots.com'}>`,
        to: email,
        subject: `Subscription Confirmed: ${botName}`,
        text: plainText,
        html: htmlContent
      }).then(info => {
        if (info.host === 'smtp.ethereal.email') {
          console.log('Preview URL: %s', nodemailer.getTestMessageUrl(info));
        }
        console.log(`Email successfully sent to ${email}`);
      }).catch(e => {
        console.error('--- EMAIL ERROR ---');
        console.error('Code:', e.code);
        console.error('Response:', e.response);
        console.error('Message:', e.message);
        console.error('-------------------');
      });
    } else {
      console.warn('Transporter not ready, email not sent.');
    }

    res.json({ 
      message: `Subscription to ${botId} successful! Credentials sent to ${email}.`,
      credentials: needsStaff ? { username: req.user.username, password: staffPassword } : null
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
});

// Admin Route
apiRouter.get('/admin/metrics', authenticateToken, requireAdmin, async (req, res) => {
  try {
    const totalUsers = await User.countDocuments();
    const totalSubscriptions = await Subscription.countDocuments({ active: true });
    
    // Aggregate Token Usages
    const tokenStats = await TokenUsage.aggregate([
      {
        $group: {
          _id: { botName: "$botName", userId: "$userId" },
          totalTokens: { $sum: "$tokensUsed" }
        }
      },
      {
        $lookup: {
          from: 'users',
          localField: '_id.userId',
          foreignField: '_id',
          as: 'user'
        }
      },
      { $unwind: "$user" },
      {
        $project: {
          botName: "$_id.botName",
          username: "$user.username",
          tokensUsed: "$totalTokens",
          _id: 0
        }
      },
      { $sort: { tokensUsed: -1 } }
    ]);

    res.json({
      totalUsers,
      totalSubscriptions,
      tokenStats
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to aggregate metrics' });
  }
});

const RATE_PER_TOKEN = 0.05; // PKR per token

apiRouter.get('/billing', authenticateToken, async (req, res) => {
  try {
    const isAdmin = req.user.role === 'admin';
    
    if (isAdmin) {
      // Admin view: Show all users and their total bills
      const allBills = await TokenUsage.aggregate([
        { $group: { _id: "$userId", totalTokens: { $sum: "$tokensUsed" } } },
        { $lookup: { from: 'users', localField: '_id', foreignField: '_id', as: 'user' } },
        { $unwind: '$user' },
        { 
          $project: { 
            username: '$user.username', 
            totalTokens: 1, 
            bill: { $multiply: ['$totalTokens', RATE_PER_TOKEN] } 
          } 
        },
        { $sort: { bill: -1 } }
      ]);
      return res.json(allBills);
    }

    // User view: Show specific user breakdown
    const userId = req.user.id;
    const userBilling = await TokenUsage.aggregate([
      { 
        $match: { 
          $or: [
            { userId: new mongoose.Types.ObjectId(userId) },
            { userId: userId }
          ]
        } 
      },
      {
        $group: {
          _id: "$botName",
          tokens: { $sum: "$tokensUsed" },
          cost: { $sum: { $multiply: ["$tokensUsed", RATE_PER_TOKEN] } }
        }
      }
    ]);

    const total = userBilling.reduce((acc, curr) => ({
      tokens: acc.tokens + (curr.tokens || 0),
      cost: acc.cost + (curr.cost || 0)
    }), { tokens: 0, cost: 0 });

    res.json({
      breakdown: userBilling || [],
      totalTokens: total.tokens || 0,
      totalBill: total.cost || 0
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch billing data' });
  }
});

app.use('/api', apiRouter);

const server = app.listen(PORT, () => {
  console.log(`Main Backend Server running on port ${PORT}`);
  console.log('Bot API targets:', BOT_API_URLS);
});

// ──────────────────────────────────────────────────────────────────
// AUTO BOT MANAGER — Spawn Python Bot APIs from Node.js with delay
// ──────────────────────────────────────────────────────────────────
const ROOT_DIR = path.join(__dirname, '..');
const BOTS = [
  { name: 'FirstAid API', cwd: path.join(ROOT_DIR, 'firstaid', 'backend'), cmd: 'python', args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8510', '--reload'] },
  { name: 'HisabBot', cwd: path.join(ROOT_DIR, 'hisabbot'), cmd: 'python', args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8511', '--reload'] },
  { name: 'PakOrderBot', cwd: path.join(ROOT_DIR, 'pakorderbot'), cmd: 'python', args: ['-m', 'uvicorn', 'agent.main:app', '--host', '127.0.0.1', '--port', '8512', '--reload'] },
  { name: 'LawBot', cwd: path.join(ROOT_DIR, 'lawyerbot'), cmd: 'python', args: ['-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', '8513', '--reload'] },
  { name: 'PakOrderBot UI', cwd: path.join(ROOT_DIR, 'pakorderbot', 'frontend'), cmd: 'python', args: ['-m', 'streamlit', 'run', 'app.py', '--server.port', '8501', '--server.headless', 'true'] }
];

const childProcesses = [];

const startBotsSequentially = async () => {
  // ── Pre-startup Cleanup ──────────────────────────────────────
  console.log('[BotManager] Cleaning up existing bot processes...');
  try {
    const ports = [8501, 8510, 8511, 8512, 8513, 8514];
    for (const port of ports) {
      if (process.platform === 'win32') {
        const killCmd = `powershell "Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"`;
        const killer = spawn(killCmd, { shell: true });
        killer.on('error', err => console.error(`[BotManager] Cleanup error for port ${port}:`, err.message));
      }
    }
    await new Promise(r => setTimeout(r, 1000));
  } catch (e) {
    console.warn('[BotManager] Cleanup warning:', e.message);
  }

  for (const bot of BOTS) {
    console.log(`\n[BotManager] Spawning ${bot.name}...`);
    const child = spawn(bot.cmd, bot.args, {
      cwd: bot.cwd,
      shell: true, 
      stdio: 'pipe'
    });

    child.on('error', err => {
      console.error(`[BotManager] Failed to start ${bot.name}:`, err.message);
      if (err.code === 'ENOENT') {
        console.error(`[BotManager] Check if directory exists: ${bot.cwd}`);
      }
    });
    
    child.stdout.on('data', data => console.log(`[${bot.name}] ${data.toString().trim()}`));
    child.stderr.on('data', data => console.error(`[${bot.name} ERR] ${data.toString().trim()}`));
    child.on('close', code => console.log(`[${bot.name}] Exited with code ${code}`));
    
    childProcesses.push(child);
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  console.log('\n[BotManager] All backends spawned!\n');
};

const cleanupBots = () => {
  console.log('\n[BotManager] Stopping all bot processes...');
  childProcesses.forEach(child => {
    if (!child.killed) {
      try { child.kill(); } catch (e) { }
    }
  });
};

process.on('SIGINT', () => { cleanupBots(); process.exit(); });
process.on('SIGTERM', () => { cleanupBots(); process.exit(); });
process.on('SIGUSR2', () => { cleanupBots(); process.exit(); });

let cleanedUp = false;
process.on('exit', () => {
  if (!cleanedUp) {
    cleanedUp = true;
    cleanupBots();
  }
});

startBotsSequentially();
 
 
 
 
 
