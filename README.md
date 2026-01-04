# 🤖 SIP Elfak Bot

Fast, robust scraper and Discord notifier for [SIP Elfak](https://sip.elfak.ni.ac.rs/).

## 🎯 Features

- **Lightning-fast scraping** using `httpx` (async) + `selectolax` (Rust-based parser)
- **Discord notifications** via webhook with rich embeds
- **Automatic deduplication** - tracks seen articles in `state.json`
- **Smart first-run** - won't spam all historical posts
- **GitHub Actions automation** - runs every 15 minutes
- **Auto-commit state** - persists tracking data back to the repo

## 📋 Requirements

- Python 3.11+
- Discord webhook URL
- GitHub repository with Actions enabled

## 🚀 Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd elfak-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Discord webhook

Create a Discord webhook:

1. Go to your Discord server settings
2. Navigate to Integrations → Webhooks
3. Click "New Webhook"
4. Copy the webhook URL

### 4. Set up GitHub Secrets

1. Go to your repository Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `DISCORD_WEBHOOK`
4. Value: Your Discord webhook URL

### 5. Enable GitHub Actions

The workflow is defined in [.github/workflows/sip.yml](.github/workflows/sip.yml) and will:

- Run automatically every 15 minutes
- Check for new posts
- Send Discord notifications
- Commit updated `state.json` back to the repo

You can also trigger it manually via the Actions tab.

## 🧪 Local Testing

Run the scraper locally:

```bash
# Set the webhook URL
export DISCORD_WEBHOOK="your-webhook-url-here"

# Run the scraper
python watcher.py
```

On Windows (PowerShell):

```powershell
$env:DISCORD_WEBHOOK = "your-webhook-url-here"
python watcher.py
```

## 📁 Files

- **`watcher.py`** - Main scraper script
- **`requirements.txt`** - Python dependencies
- **`state.json`** - Tracks seen articles (auto-updated)
- **`.github/workflows/sip.yml`** - GitHub Actions workflow

## 🔧 Configuration

Edit these constants in `watcher.py`:

```python
BASE_URL = "https://sip.elfak.ni.ac.rs"
SOURCES = [
    {"url": f"{BASE_URL}/", "name": "Naslovna"},
    {"url": f"{BASE_URL}/category/ostalo", "name": "Ostalo"},
]
RATE_LIMIT_SLEEP = 0.7  # seconds between article fetches
MAX_INITIAL_POSTS = 3   # max posts to announce on first run
```

## 🆕 Recent Improvements

- **Chronological posting**: All Discord notifications are sent in order of article publication date (oldest first).
- **Deduplication by title and content**: Bot will not post duplicate articles even if URLs differ, as long as title and first 500 characters of content match.
- **Accurate timestamp**: Discord embed timestamp matches the actual article date and time (e.g. "Сре, 31. Дец, 2025. у 12:48"), not the time of posting.
- **Bot profile and avatar**: Bot uses the name "Elfak SIP" and attempts to use the official Elfak logo as avatar (requires public PNG/JPG URL).
- **Date filtering**: Only articles published after December 1, 2025 are posted to Discord.
- **Serbian date parsing**: Supports Cyrillic month names and parses time ("у HH:MM") for precise timestamps.

## 🎨 Discord Embed Format (Updated)

- **Title**: Article title (clickable link)
- **URL**: Direct link to the article
- **Description**: Full content, formatted with Markdown (bold, links, lists)
- **Category & Date**: Shown as embed fields
- **Image/Thumbnail**: If available
- **Color**: Bright blue
- **Timestamp**: Actual article date/time
- **Footer**: "SIP Elfak Bot"
- **Bot name**: "Elfak SIP"
- **Avatar**: Elfak logo (if public URL is available)

## 🛡️ How it works (Updated)

1. **Scraping**: Fetches all 15 SIP categories
2. **Article extraction**: Finds all `/article/` links and extracts titles, dates, and content
3. **Deduplication**: Uses title + content for uniqueness, not just URL
4. **Date extraction**: Parses Serbian date format including time
5. **State management**: Compares against `state.json` to find new articles
6. **Date filtering**: Skips articles before Dec 1, 2025
7. **Chronological posting**: Sorts articles by publication date before sending
8. **Rate limiting**: Sleeps 2s between Discord posts
9. **Discord notification**: Sends rich embeds for each new article
10. **State persistence**: Updates `state.json` and commits back to repo

## 📊 Performance

- **Async I/O**: Concurrent HTTP requests with `httpx`
- **Fast parsing**: `selectolax` is 5-25x faster than BeautifulSoup
- **Smart caching**: GitHub Actions uses pip cache
- **Minimal overhead**: Typically completes in 5-15 seconds

## 🐛 Troubleshooting (Updated)

- **No avatar?** Make sure the logo URL is a public PNG/JPG. Discord may not support SVG or private links.
- **Wrong timestamp?** Check that the article date is in the expected Serbian format (e.g. "у HH:MM").
- **Duplicates?** Only truly identical title+content will be skipped; minor changes will be posted.
- **Missing articles?** Only posts after Dec 1, 2025 are sent.

## 📝 License

See [LICENSE](LICENSE) file.

## 🙏 Credits

Built with:

- [httpx](https://www.python-httpx.org/) - Fast async HTTP client
- [selectolax](https://github.com/rushter/selectolax) - Fast HTML parser
- GitHub Actions for automation
