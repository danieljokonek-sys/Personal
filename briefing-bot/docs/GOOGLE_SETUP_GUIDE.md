# Google Cloud Setup Guide
### Personal Communication Tracker

This guide walks you through the Google Cloud setup required to let the app read your Gmail and Google Calendar. You only need to do this once.

**Total time: about 10–15 minutes**

---

## Step 1 — Create a Google Cloud Project

1. Go to **https://console.cloud.google.com**
2. Sign in with your Google account (the main one you want to track)
3. At the top of the page, click the project dropdown (it may say "Select a project" or show an existing project name)
4. Click **New Project**
5. Name it anything — e.g. `Personal Tracker`
6. Click **Create**
7. Wait a few seconds, then make sure your new project is selected in the dropdown at the top

---

## Step 2 — Enable the Gmail API

1. In the left sidebar, click **APIs & Services** → **Library**
2. In the search box, type **Gmail API**
3. Click on **Gmail API** in the results
4. Click the blue **Enable** button
5. Wait for it to enable (10–15 seconds)

---

## Step 3 — Enable the Google Calendar API

1. Click the back arrow or go to **APIs & Services** → **Library** again
2. Search for **Google Calendar API**
3. Click on **Google Calendar API**
4. Click **Enable**

---

## Step 4 — Configure the OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** and click **Create**
3. Fill in the required fields:
   - **App name:** Personal Tracker (or anything you like)
   - **User support email:** your Gmail address
   - **Developer contact email:** your Gmail address
4. Click **Save and Continue**
5. On the **Scopes** page — click **Save and Continue** (no changes needed)
6. On the **Test users** page:
   - Click **Add Users**
   - Add **every Gmail address** you want to track
   - Click **Save and Continue**
7. Click **Back to Dashboard**

---

## Step 5 — Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** at the top
3. Choose **OAuth client ID**
4. For **Application type**, select **Desktop app**
5. Name it anything — e.g. `Tracker Desktop`
6. Click **Create**
7. A popup will appear — click **Download JSON**
8. This downloads a file with a long name like `client_secret_123456...json`

---

## Step 6 — Place the Credentials File

1. Rename the downloaded file to exactly: **`credentials.json`**
2. Move it into the `credentials` folder inside the app folder:
   ```
   briefing-bot/
     credentials/
       credentials.json   ← put it here
   ```

---

## Step 7 — Return to the Setup Wizard

Go back to the setup wizard and click **"I've completed these steps"**. It will check that the file is in the right place and proceed to authorize your Gmail accounts.

---

## Troubleshooting

**"Access blocked" when authorizing Gmail**
→ You need to add your email as a Test User (Step 4, point 6 above)

**"APIs not enabled" error**
→ Double-check Steps 2 and 3 — make sure both Gmail API and Calendar API show as "Enabled"

**Can't find the credentials folder**
→ It's inside the briefing-bot app folder, same place as this guide

**Still stuck?**
→ Email the person who shared this app with you and include a screenshot of the error
