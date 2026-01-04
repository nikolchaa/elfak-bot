# Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Get Your Discord Webhook

1. Open Discord and go to your server
2. Go to **Server Settings** → **Integrations** → **Webhooks**
3. Click **New Webhook** (or **Create Webhook**)
4. Give it a name like "SIP Elfak Notifier"
5. Choose the channel where you want notifications
6. Click **Copy Webhook URL**
7. Save this URL - you'll need it next!

### Step 2: Add Webhook to GitHub Secrets

1. Go to your GitHub repository
2. Click **Settings** (top menu)
3. In the left sidebar: **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. Name: `DISCORD_WEBHOOK`
6. Value: Paste your webhook URL
7. Click **Add secret**

### Step 3: Push Code to GitHub

```bash
git add .
git commit -m "Initial setup"
git push
```

### Step 4: Enable GitHub Actions

1. Go to the **Actions** tab in your repository
2. If prompted, click **I understand my workflows, go ahead and enable them**
3. You should see the "SIP Elfak Watcher" workflow

### Step 5: Test It!

**Option A: Wait for automatic run** (next 15-minute interval)

**Option B: Manual trigger** (instant)

1. Click on **SIP Elfak Watcher** workflow
2. Click **Run workflow** dropdown
3. Click **Run workflow** button
4. Wait ~30 seconds
5. Check your Discord channel! 🎉

## ✅ What to Expect

### First Run

- Bot will find existing articles
- Will notify you of the **3 most recent** posts only
- All others are marked as "seen" (no spam!)
- `state.json` gets committed to the repo

### Subsequent Runs (every 15 min)

- Bot checks for **new** articles only
- Sends Discord embed for each new post
- Updates `state.json` automatically

## 🧪 Local Testing (Optional)

Want to test before pushing to GitHub?

```bash
# Install dependencies
pip install -r requirements.txt

# Set webhook (Linux/Mac)
export DISCORD_WEBHOOK="your-webhook-url"

# Set webhook (Windows PowerShell)
$env:DISCORD_WEBHOOK = "your-webhook-url"

# Run the bot
python watcher.py
```

You should see output like:

```
🚀 SIP Elfak Bot starting...
⏰ Timestamp: 2026-01-04T10:15:00.000Z
📋 Loaded state: 0 URLs already seen
🔍 Scraping: https://sip.elfak.ni.ac.rs/
📄 Extracted 15 articles from Naslovna
🔍 Scraping: https://sip.elfak.ni.ac.rs/category/ostalo
📄 Extracted 8 articles from Ostalo
📊 Total unique articles found: 20
🆕 New articles: 20
⚡ First run detected - limiting to 3 most recent posts

🔔 Processing 1/3: Važno obaveštenje...
✅ Discord notification sent: Važno obaveštenje
...
✅ State saved: 20 URLs tracked
✨ Done! Processed 3 new articles.
```

## 🎯 Verify It's Working

Check these indicators:

1. **GitHub Actions**

   - Go to **Actions** tab
   - See green checkmarks ✅
   - Click on latest run to see logs

2. **Discord Channel**

   - See new message from your webhook
   - Rich embed with blue color
   - Title is clickable link

3. **Repository**
   - `state.json` file updated
   - Commit message: "🤖 Update state.json [skip ci]"

## 🔧 Customize

Edit [watcher.py](watcher.py) to change:

```python
# Check more pages
SOURCES = [
    {"url": f"{BASE_URL}/", "name": "Naslovna"},
    {"url": f"{BASE_URL}/category/ostalo", "name": "Ostalo"},
    {"url": f"{BASE_URL}/category/vesti", "name": "Vesti"},  # Add more!
]

# Faster/slower scraping
RATE_LIMIT_SLEEP = 0.7  # seconds

# More posts on first run
MAX_INITIAL_POSTS = 3  # increase if you want
```

Edit [.github/workflows/sip.yml](.github/workflows/sip.yml) to change schedule:

```yaml
schedule:
  - cron: "*/15 * * * *" # Every 15 minutes
  # - cron: '*/5 * * * *'   # Every 5 minutes
  # - cron: '0 * * * *'     # Every hour
  # - cron: '0 */2 * * *'   # Every 2 hours
```

## ❓ Troubleshooting

**"No Discord notifications"**

- Check that `DISCORD_WEBHOOK` secret is set correctly
- Verify webhook URL works by pasting it in a tool like Postman
- Check GitHub Actions logs for errors

**"Duplicate notifications"**

- This shouldn't happen if `state.json` is being committed
- Check the Actions logs to see if commit/push is working
- Verify git permissions in workflow

**"Missing new posts"**

- The site might have changed structure
- Check the scraper logs in GitHub Actions
- Open an issue with details

## 🆘 Need Help?

- Check [README.md](README.md) for full documentation
- Review [GitHub Actions logs](../../actions)
- Check [DISCORD_EXAMPLE.md](DISCORD_EXAMPLE.md) for embed format

---

**That's it!** Your bot is now watching SIP Elfak 24/7 and will ping you whenever something new appears. 🎉
