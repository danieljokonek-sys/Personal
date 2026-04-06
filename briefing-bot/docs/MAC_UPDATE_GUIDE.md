# What To Do When macOS Updates
### Personal Communication Tracker — Maintenance Guide

This guide covers what to check and fix after your Mac receives a software update.
Most updates require nothing. Occasionally one of the steps below will be needed.

---

## After ANY macOS Update — Quick Checklist

Run through these in order. Stop when your daily briefing is working again.

### 1. Check if the daily briefing still arrives
Wait until the next morning. If the email arrives — you're done, nothing broke.

### 2. If no email — test manually
Open Terminal and run:
```bash
cd ~/briefing-bot
python3 main.py run
```
Read any error messages and match them to the sections below.

---

## Common Issues After macOS Updates

---

### A. "python3: command not found" or "No module named click/anthropic/etc."

**What happened:** macOS updates sometimes reset or replace the system Python installation, or Homebrew's Python path changes.

**Fix:**
```bash
# Reinstall dependencies
cd ~/briefing-bot
bash install.sh
```
The installer is safe to re-run — it won't erase your data or settings. It will reinstall Python and all packages.

---

### B. Daily briefing stopped arriving (no error when run manually)

**What happened:** macOS updates sometimes disable or remove launchd scheduled tasks.

**Fix — re-register the daily schedule:**
```bash
# Remove old schedule
launchctl unload ~/Library/LaunchAgents/com.personaltracker.daily.plist 2>/dev/null

# Re-register it
launchctl load ~/Library/LaunchAgents/com.personaltracker.daily.plist

# Verify it's loaded
launchctl list | grep personaltracker
```
You should see `com.personaltracker.daily` in the output. If the plist file is missing entirely, re-run the setup wizard:
```bash
python3 setup_wizard.py
```

---

### C. "Gmail authorization failed" or "Token invalid/expired"

**What happened:** macOS updates can clear keychain entries or invalidate OAuth tokens. Google also periodically expires tokens on its own (unrelated to macOS updates).

**Fix — re-authorize Gmail:**
```bash
cd ~/briefing-bot
rm -f credentials/token_*.json
python3 main.py setup-accounts
```
This opens a browser window for each Gmail account. Sign in and approve access. Your emails and data are not affected.

---

### D. "SSL certificate verify failed" or network errors

**What happened:** macOS updates sometimes change the system SSL certificate store that Python relies on.

**Fix:**
```bash
# Update Python certificates
/Applications/Python\ 3.11/Install\ Certificates.command
```
If that file doesn't exist, try:
```bash
pip3 install --upgrade certifi
```

---

### E. Google API errors — "Access blocked" or "Insufficient permissions"

**What happened:** Google occasionally tightens OAuth policies, especially for apps in "testing" mode. After one year, test-mode OAuth tokens expire and all authorized users are logged out.

**Fix:**
1. Go to console.cloud.google.com
2. Select your project → **APIs & Services → OAuth consent screen**
3. If it says your app's test users have been removed or the app needs to be re-verified — re-add yourself as a test user
4. Then re-authorize Gmail:
```bash
rm -f credentials/token_*.json
python3 main.py setup-accounts
```

**Note:** Google expires test-mode apps after **1 year**. Set a calendar reminder to re-add test users each year, or publish the app (free, requires a short review process).

---

### F. Anthropic API errors — "Invalid API key" or "Credit balance too low"

**What happened:** Unrelated to macOS — your API key may have been revoked, or your credit balance ran out.

**Fix:**
1. Go to console.anthropic.com → **Billing** — top up credits if low
2. Go to **API Keys** — create a new key if needed
3. Open the `.env` file in the Personal folder and update the key:
```bash
nano ~/briefing-bot/.env
```
Change the line to:
```
ANTHROPIC_API_KEY=sk-ant-YOUR-NEW-KEY-HERE
```
Press `Ctrl+X`, then `Y`, then `Enter` to save.

---

### G. App crashes with unfamiliar Python errors after update

**What happened:** A major macOS update (e.g. Sonoma → Sequoia) may install a new version of Python that has compatibility issues with older package versions.

**Fix — lock to a known working Python version:**
```bash
# Install a specific Python version via Homebrew
brew install python@3.11

# Re-run the installer pointing at that version
python3.11 -m pip install -r ~/briefing-bot/requirements.txt
```
Then update the launchd plist to use `python3.11` explicitly instead of `python3`.

---

## Annual Maintenance (Set a Calendar Reminder)

Do these once a year to prevent issues before they happen:

| Task | Why |
|---|---|
| Re-add Gmail test users in Google Cloud Console | Google expires test apps after 12 months |
| Check Anthropic credit balance | Avoid unexpected API shutoff |
| Run `pip3 install -r requirements.txt --upgrade` | Keep packages current |
| Run `python3 main.py run` manually | Confirm end-to-end pipeline works |

---

## If Nothing Works

Contact the person who set this up for you and send them:
1. A screenshot of the Terminal error
2. The output of: `python3 --version`
3. What macOS version you updated to (Apple menu → About This Mac)

---

## Your Key File Locations

| File | Location | What it does |
|---|---|---|
| App folder | `~/briefing-bot/` | Everything lives here |
| API key | `~/briefing-bot/.env` | Anthropic access |
| Gmail tokens | `~/briefing-bot/credentials/token_*.json` | Gmail authorization |
| Google credentials | `~/briefing-bot/credentials/credentials.json` | Google Cloud OAuth client |
| Schedule | `~/Library/LaunchAgents/com.personaltracker.daily.plist` | Daily 8am trigger |
| Database | `~/briefing-bot/data/tracker.db` | All your tracked data |
