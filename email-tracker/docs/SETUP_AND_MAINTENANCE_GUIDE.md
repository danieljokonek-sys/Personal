# Personal Communication Tracker
## Complete Setup & Maintenance Guide

*Written for non-technical users. No prior experience needed.*

---

# PART 1 — FIRST TIME SETUP

---

## Before You Start

You will need:
- A **Mac computer** (this guide is Mac only)
- A **Gmail account** (the one you want tracked)
- A **credit card** (to purchase ~$10 in AI credits — one-time, lasts months)
- About **30–45 minutes** of uninterrupted time

---

## Section 1 — Get Your AI Credit (Anthropic API Key)

This is what powers the intelligent part of the app — reading your emails and writing your daily briefing.

1. Open Safari or Chrome and go to: **https://console.anthropic.com**
2. Click **Sign Up** and create an account with your email
3. Verify your email when the confirmation arrives
4. Once logged in, click **Billing** in the left sidebar
5. Click **Add payment method** and enter your credit card
6. Click **Buy credits** and purchase **$10** (this lasts 3–6 months of daily use)
7. Now click **API Keys** in the left sidebar
8. Click **+ Create Key**, give it any name (e.g. "My Tracker"), click **Create**
9. A long code appears starting with `sk-ant-` — **copy it and paste it somewhere safe** (a Notes document is fine). You will need it during setup. **You can only see it once.**

---

## Section 2 — Set Up Google Cloud Access

This is what allows the app to read your Gmail and Calendar. It sounds technical but just follow each step exactly as written.

**Step 2a — Create a Google Project**

1. Go to: **https://console.cloud.google.com**
2. Sign in with the Gmail account you want to track
3. At the very top of the page, click the dropdown that says **"Select a project"**
4. Click **New Project** in the top right of the popup
5. In the Name field type: `Personal Tracker`
6. Click **Create**
7. Wait about 10 seconds. Click the dropdown again and select **Personal Tracker**

**Step 2b — Turn On Gmail Access**

1. In the left sidebar, click **APIs & Services**, then **Library**
2. In the search box type: `Gmail API`
3. Click **Gmail API** in the results
4. Click the blue **Enable** button
5. Wait for the green checkmark

**Step 2c — Turn On Calendar Access**

1. Click the back arrow, or click **Library** in the left sidebar again
2. Search for: `Google Calendar API`
3. Click **Google Calendar API**
4. Click **Enable**

**Step 2d — Set Up the Consent Screen**

1. In the left sidebar click **OAuth consent screen**
2. Select **External**, click **Create**
3. Fill in:
   - App name: `Personal Tracker`
   - User support email: *your Gmail address*
   - Developer contact email: *your Gmail address*
4. Click **Save and Continue**
5. On the next screen (Scopes) — click **Save and Continue** without changing anything
6. On the next screen (Test Users):
   - Click **+ Add Users**
   - Type in your Gmail address and press Enter
   - If you have more Gmail accounts to track, add those too
   - Click **Save and Continue**
7. Click **Back to Dashboard**

**Step 2e — Create Your Credentials File**

1. In the left sidebar click **Credentials**
2. Click **+ Create Credentials** at the top, choose **OAuth client ID**
3. For Application type choose: **Desktop app**
4. Name it: `Tracker Desktop`
5. Click **Create**
6. A popup appears — click **Download JSON**
7. A file downloads to your Downloads folder with a long complicated name
8. **Rename that file to exactly:** `credentials.json` (all lowercase, no spaces)
9. Leave it in your Downloads folder for now — you'll move it in the next section

---

## Section 3 — Install the App

1. Copy the **email-tracker** folder onto your Mac desktop
2. Open the **email-tracker** folder — you should see files including `install.sh`
3. Move the `credentials.json` file from your Downloads folder into the **credentials** folder inside email-tracker:
   ```
   email-tracker/
     credentials/
       credentials.json   ← put it here
   ```
4. Open **Terminal**:
   - Press `Command + Space` on your keyboard
   - Type `Terminal`
   - Press Enter
5. Type the following and press Enter:
   ```
   bash ~/email-tracker/install.sh
   ```
6. Your Mac may ask for your password — type it and press Enter (the characters won't show, that's normal)
7. Wait while it installs. This takes 2–5 minutes. You'll see text scrolling — that's normal.
8. A **setup window** will appear on screen when it's ready

---

## Section 4 — Complete the Setup Wizard

A window will open and walk you through the remaining steps. Here's what each screen asks:

**Screen 1 — Welcome**
Click **Next**

**Screen 2 — API Key**
Paste the `sk-ant-` code you saved from Section 1. Click **Next**.

**Screen 3 — Your Email Accounts**
Choose how many Gmail accounts you want tracked (1, 2, or 3).
Enter the name and email address for each one. Click **Next**.

**Screen 4 — Your Businesses / Life Areas**
Fill in what you want tracked. Examples:
- Name: `My Freelance Work` / Description: `Client projects and invoices`
- Name: `Rental Property` / Description: `Tenant communications and rent`
- Name: `Personal` / Description: `General life admin`
Leave any rows blank that you don't need. Click **Next**.

**Screen 5 — Digest Settings**
- Enter the email address where you want your daily briefing sent
- Choose what time you want it (8:00 AM is the default)
Click **Next**.

**Screen 6 — Google Cloud Check**
Click **Check File**. If it says ✓ Found — click **Next**.
If it says not found — make sure you placed `credentials.json` in the credentials folder (Step 3 above) and try again.

**Screen 7 — Authorize Gmail**
Click **Authorize Accounts**. A browser window will open.
- Sign into the correct Google account when prompted
- Click **Allow** when Google asks for permission
- Repeat for each account if you set up more than one
- Return to the wizard when done. Click **Next**.

**Screen 8 — Done!**
Your app is set up. Click **Finish**.

---

## Section 5 — Test It

To make sure everything is working, open Terminal and run:
```
cd ~/email-tracker
python3 main.py run
```

You should see text scrolling as it fetches your emails and calendar. After 1–2 minutes, check your inbox — your first briefing email should arrive.

**From now on, this runs automatically every morning.** You don't need to do anything.

---
---

# PART 2 — ONGOING MAINTENANCE

---

Most of the time you'll need to do nothing. Your briefing will just arrive each morning. Below are the only situations that require action.

---

## Situation 1 — Your Daily Briefing Stopped Arriving

**First, wait one day.** If your Mac was asleep at the scheduled time, the briefing fires the next time you log in.

**If it's been two days:**

Open Terminal and run:
```
cd ~/email-tracker
python3 main.py run
```

Read any red error text and find the matching situation below.

---

## Situation 2 — Error Says "Gmail authorization failed" or "Token expired"

Google periodically requires you to re-authorize. Takes 2 minutes.

```
cd ~/email-tracker
rm credentials/token_*.json
python3 main.py setup-accounts
```

A browser window opens. Sign into your Google account and click Allow.
Done — your briefings will resume.

**This also happens after macOS updates.** Same fix.

---

## Situation 3 — Error Says "python3: command not found" or "No module named..."

A Mac update replaced or moved your Python installation.

```
cd ~/email-tracker
bash install.sh
```

The installer is safe to re-run. It won't delete any of your data.

---

## Situation 4 — Error Says "Credit balance too low"

Your Anthropic credits ran out.

1. Go to **https://console.anthropic.com**
2. Click **Billing** → **Buy credits**
3. Purchase $10 or more
4. Run your briefing again:
   ```
   python3 ~/email-tracker/main.py run
   ```

---

## Situation 5 — Error Says "Access blocked" when authorizing Gmail

Google removed your test user access (this happens automatically after 12 months).

1. Go to **https://console.cloud.google.com**
2. Select your **Personal Tracker** project
3. Click **APIs & Services** → **OAuth consent screen**
4. Scroll to **Test users** → click **+ Add Users**
5. Re-add your Gmail address(es) → click **Save**
6. Then in Terminal:
   ```
   rm ~/email-tracker/credentials/token_*.json
   python3 ~/email-tracker/main.py setup-accounts
   ```

---

## Situation 6 — The Briefing Schedule Stopped After a macOS Update

```
launchctl unload ~/Library/LaunchAgents/com.personaltracker.daily.plist
launchctl load ~/Library/LaunchAgents/com.personaltracker.daily.plist
```

---

## Situation 7 — You Want to Change What Time the Briefing Arrives

Open Terminal:
```
python3 ~/email-tracker/setup_wizard.py
```

Go through the wizard again. On the Digest Settings screen, change the time.

---

## Situation 8 — Something Else Is Wrong

1. Open Terminal and run:
   ```
   cd ~/email-tracker
   python3 main.py run
   ```
2. Take a screenshot of everything in the Terminal window
3. Note your macOS version: click the **Apple menu** (top left) → **About This Mac**
4. Send both to the person who set this up for you

---
---

# PART 3 — USEFUL DAILY COMMANDS

---

You can run any of these anytime in Terminal. They don't affect your scheduled briefing.

**Get your briefing right now (don't wait for morning):**
```
cd ~/email-tracker
python3 main.py run
```

**See what's coming up in the next 14 days:**
```
python3 main.py horizon
```

**Add a task to your to-do list:**
```
python3 main.py tasks add "Call insurance company" --priority high
python3 main.py tasks add "File taxes" --due 2026-04-15 --priority high
```

**See your task list:**
```
python3 main.py tasks list
```

**Mark a task done:**
```
python3 main.py tasks done 3
```
*(Replace 3 with the task number shown in the list)*

**See emails you're waiting for a reply on:**
```
python3 main.py followups list
```

**Dismiss a follow-up you no longer need:**
```
python3 main.py followups dismiss 2
```

**Snooze something so it stops appearing for a few days:**
```
python3 main.py snooze item action_items 5 3d
python3 main.py snooze item tasks 1 1w
```

**See everything that's snoozed:**
```
python3 main.py snooze list
```

**See your overall dashboard:**
```
python3 main.py status
```

---
---

# PART 4 — ANNUAL REMINDERS

Set these as repeating calendar events so problems never sneak up on you.

---

### Every 12 Months — Re-add Google Test Users

Google automatically removes access for apps in "test mode" after one year.

1. Go to **https://console.cloud.google.com**
2. Select **Personal Tracker** project
3. **APIs & Services** → **OAuth consent screen**
4. **Test users** → **+ Add Users** → re-add your Gmail addresses → **Save**
5. Then re-authorize:
   ```
   rm ~/email-tracker/credentials/token_*.json
   python3 ~/email-tracker/main.py setup-accounts
   ```

---

### Every 3–6 Months — Check Anthropic Credit Balance

1. Go to **https://console.anthropic.com**
2. Click **Billing**
3. If balance is below $5, top up

---

### After Every macOS Major Update (e.g. Sequoia → next version)

Run these three things in order:

```
cd ~/email-tracker
bash install.sh
rm credentials/token_*.json
python3 main.py setup-accounts
```

Then test:
```
python3 main.py run
```

---
---

# QUICK REFERENCE CARD

*Print this page and keep it somewhere handy*

| Problem | Fix |
|---|---|
| No briefing email | Run `python3 main.py run` and check for errors |
| Gmail auth failed | Delete tokens, run `setup-accounts` |
| Python not found | Re-run `install.sh` |
| Credits ran out | Top up at console.anthropic.com |
| Access blocked by Google | Re-add test users in Google Cloud Console |
| Schedule stopped | Reload with `launchctl` commands |
| Something else | Screenshot Terminal + send to your contact |

**Your app folder:** `~/email-tracker/`
**Your API key file:** `~/email-tracker/.env`
**Your Google credentials:** `~/email-tracker/credentials/`
**Anthropic billing:** https://console.anthropic.com
**Google Cloud:** https://console.cloud.google.com
