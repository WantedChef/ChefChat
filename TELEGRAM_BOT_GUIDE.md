# 🤖 ChefChat Telegram Bot - Complete Gids

## 📱 **Mini App URL Configuratie**

### **Current URL**
De publieke URL waar je Mini App bereikbaar is.

**Voorbeelden:**
- Cloudflare Tunnel: `https://your-tunnel.trycloudflare.com/`
- ngrok: `https://abc123.ngrok.io`
- Eigen domein: `https://chefchat.yourdomain.com`

### **Mode**
- **Fullsize**: Mini app vult hele Telegram scherm (aanbevolen)
- **Compact**: Kleiner venster

### **Splash Icon**
- **Default**: Telegram's standaard icoon
- **Custom**: Upload eigen icoon (moet je configureren)

### **Background Color & Header Color**
- **Default**: Telegram's thema kleuren
- **Custom**: Eigen kleuren in hex formaat
  - ChefChat oranje: `#FF7000`
  - Donker: `#1a1a1a`
  - Licht: `#ffffff`

---

## 🌐 **Cloudflare Tunnel CIDR Configuratie**

### **CIDR** (Required)
Privé netwerk range voor tunnel routing.

**Aanbevolen waarden:**
```
10.0.0.0/8          # Breed privé netwerk
192.168.0.0/16      # Lokale netwerken
172.16.0.0/12       # Docker/containers
127.0.0.1/32        # Alleen localhost
```

### **Description** (Required)
```
ChefChat Mini App - Private Network Access
```

### **Waarom?**
Dit zorgt ervoor dat Cloudflare Tunnel verkeer kan routeren naar je lokale Mini App server (`127.0.0.1:8088`).

---

## 🎯 **Alle Bot Commands**

### **Basis Commands**
| Command | Beschrijving |
|---------|-------------|
| `/start` | Start de bot en toon welkomstbericht |
| `/stop` | Stop huidige sessie en clear data |
| `/clear` | Clear conversatie geschiedenis |
| `/help` | Toon alle beschikbare commands |

### **Informatie Commands**
| Command | Beschrijving |
|---------|-------------|
| `/status` | Bot status, uptime, working dir |
| `/stats` | Gedetailleerde sessie statistieken |
| `/files` | List project files (max 30) |
| `/pwd` | Toon current working directory |

### **Model Commands**
| Command | Beschrijving |
|---------|-------------|
| `/model` | Toon current model status |
| `/model list` | List alle beschikbare models |
| `/model select <alias>` | Switch naar ander model |

### **Fun Commands** 🎉
| Command | Beschrijving |
|---------|-------------|
| `/chef` | Kitchen status report met stats |
| `/wisdom` | Culinary-inspired programming wisdom |
| `/roast` | Gordon Ramsay style motivational burns |
| `/fortune` | Developer fortune cookies |

### **Advanced Commands**
| Command | Beschrijving |
|---------|-------------|
| `/reload` | Reload configuration (hot-reload) |
| `/chefchat` | Systemd controls (als enabled) |

---

## 🔧 **Environment Variables**

### **Vereist**
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_USERS=user_id_1,user_id_2
```

### **Optioneel - Systemd Control**
```bash
CHEFCHAT_ENABLE_TELEGRAM_SYSTEMD_CONTROL=true
CHEFCHAT_TELEGRAM_UNIT_BASE=chefchat-telegram
CHEFCHAT_PROJECTS=chefchat,project2,project3
```

### **Optioneel - Bot Behavior**
```bash
CHEFCHAT_BOT_AUTO_APPROVE=true
SYSTEMCTL_BIN=/usr/bin/systemctl
```

---

## 🚀 **Bot Starten**

### **Via Systemd** (Aanbevolen)
```bash
systemctl --user start chefchat-telegram
systemctl --user status chefchat-telegram
```

### **Handmatig**
```bash
cd /home/chef/chefchat/ChefChat
uv run python -m chefchat.bots.daemon
```

### **Via ChefChat CLI**
```bash
vibe --bot telegram
```

---

## 🎨 **Fun Command Voorbeelden**

### `/chef` - Kitchen Status
```
👨‍🍳 Chef's Kitchen Report

🔥 Station: Active
⏱️ Uptime: up 2 days, 5 hours
💬 Messages: 42
📁 Workdir: /home/chef/chefchat_output_

'Mise en place, chef!' 🍽️
```

### `/wisdom` - Programming Wisdom
```
🔪 Sharp tools make clean cuts. Keep your dependencies updated.
```

### `/roast` - Gordon Ramsay Style
```
🔥 This code is so raw, it's still importing dependencies!
```

### `/fortune` - Developer Fortune
```
🥠 A bug fixed today is a feature tomorrow.
```

---

## 🔒 **Security Features**

1. **User Allowlist**: Alleen toegestane user IDs kunnen de bot gebruiken
2. **Rate Limiting**: Max 6 berichten per 30 seconden per user
3. **File Lock**: Voorkomt dubbele bot instances
4. **Access Control**: Alle commands checken allowlist
5. **Approval System**: Tool execution vereist user approval

---

## 🐛 **Troubleshooting**

### **Bot reageert niet**
```bash
# Check of bot draait
systemctl --user status chefchat-telegram

# Check logs
journalctl --user -u chefchat-telegram -f
```

### **"Lock file busy" error**
```bash
# Verwijder stale lock
rm ~/chefchat_output_/telegram_bot.lock

# Restart bot
systemctl --user restart chefchat-telegram
```

### **"Access denied" in Telegram**
```bash
# Voeg je user ID toe
vibe /telegram allow YOUR_USER_ID

# Of direct in .env
echo "TELEGRAM_ALLOWED_USERS=YOUR_USER_ID" >> .env
```

### **Commands werken niet**
```bash
# Reload bot configuration
# In Telegram: /reload

# Of restart service
systemctl --user restart chefchat-telegram
```

---

## 📊 **Performance Tips**

1. **Rate Limiting**: Pas aan in `telegram_bot.py`:
   ```python
   self._rate_limit_window_s = 30.0  # Verhoog voor meer berichten
   self._rate_limit_max_events = 6   # Verhoog limiet
   ```

2. **Session TTL**: Pas aan voor langere/kortere sessies:
   ```python
   self._session_ttl_s = 60.0 * 60.0  # 1 uur (in seconden)
   ```

3. **Message Truncation**: Verhoog limiet (max 4096):
   ```python
   TELEGRAM_MESSAGE_TRUNCATE_LIMIT = 4000
   ```

---

## 🎯 **Roadmap - Toekomstige Features**

### **Prioriteit 1** ✅
- [x] Fun easter egg commands
- [x] Retry logic voor API calls
- [x] Hot-reload configuration
- [x] Session statistics

### **Prioriteit 2** 🔄
- [ ] File upload support
- [ ] Inline queries
- [ ] Group chat support
- [ ] Custom keyboards

### **Prioriteit 3** 💡
- [ ] Metrics/analytics dashboard
- [ ] Webhook support (alternatief voor polling)
- [ ] Conversation export
- [ ] Multi-language support

---

## 📝 **Changelog**

### **v1.1.0** - 2025-12-15
- ✨ Added fun commands: `/chef`, `/wisdom`, `/roast`, `/fortune`
- ✨ Added `/stats` for detailed session statistics
- ✨ Added `/reload` for hot-reload configuration
- 🔧 Improved retry logic for Telegram API calls
- 📚 Enhanced help text with categorized commands
- 🐛 Fixed message truncation edge cases

### **v1.0.0** - Initial Release
- 🎉 Basic bot functionality
- 🔒 User allowlist system
- 🤖 ChefChat agent integration
- 🛠️ Tool approval system
- 📱 Mini App web interface

---

## 🤝 **Support**

Voor vragen of problemen:
1. Check deze documentatie
2. Check de logs: `journalctl --user -u chefchat-telegram -f`
3. Open een issue op GitHub
4. Vraag hulp in de ChefChat community

---

**Made with ❤️ by the ChefChat team**
*Type `/chef` in Telegram voor culinary inspiration!*
