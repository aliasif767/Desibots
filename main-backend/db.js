const mongoose = require('mongoose');
const bcrypt = require('bcrypt');

const MONGO_URI = process.env.MONGO_URI || 'mongodb://127.0.0.1:27017/desibots_main';

const userSchema = new mongoose.Schema({
    username: { type: String, required: true, unique: true },
    password: { type: String, required: true },
    role: { type: String, default: 'user' }
});

const subscriptionSchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    botId: { type: String, required: true },
    plan: { type: String, default: 'pro' },
    active: { type: Boolean, default: true }
});

const tokenUsageSchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    botName: { type: String, required: true },
    tokensUsed: { type: Number, required: true },
    timestamp: { type: Date, default: Date.now }
});

const whatsAppSessionSchema = new mongoose.Schema({
    phoneNumber: { type: String, required: true, unique: true },
    activeBot: { type: String, default: 'hisabot' }, // Default to hisabot
    lastInteraction: { type: Date, default: Date.now }
});

const platformSettingsSchema = new mongoose.Schema({
    key: { type: String, required: true, unique: true },
    value: { type: mongoose.Schema.Types.Mixed, required: true }
});

const User = mongoose.model('User', userSchema);
const Subscription = mongoose.model('Subscription', subscriptionSchema);
const TokenUsage = mongoose.model('TokenUsage', tokenUsageSchema);
const WhatsAppSession = mongoose.model('WhatsAppSession', whatsAppSessionSchema);
const PlatformSettings = mongoose.model('PlatformSettings', platformSettingsSchema);

async function setupDB() {
    await mongoose.connect(MONGO_URI);
    console.log("Connected to Main Backend MongoDB:", MONGO_URI);

    // Add admin user for testing
    const adminExists = await User.findOne({ username: 'admin' });
    if (!adminExists) {
        const hashedPassword = await bcrypt.hash('admin123', 10);
        await User.create({ username: 'admin', password: hashedPassword, role: 'admin' });
        console.log("Created default admin user with username: admin, password: admin123. Admin bypasses subscription checks globally.");
    }
}

module.exports = { setupDB, User, Subscription, TokenUsage, WhatsAppSession, PlatformSettings, mongoose };
