# Technical Architecture

## 🏗️ System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions (Scheduler)               │
│                    Runs every X minutes                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      watcher.py                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. Load state.json (seen URLs)                       │  │
│  │  2. Scrape target pages (async)                       │  │
│  │  3. Extract articles & titles                         │  │
│  │  4. Deduplicate by URL                                │  │
│  │  5. Find new articles (not in state)                  │  │
│  │  6. Fetch article dates (if needed)                   │  │
│  │  7. Send Discord webhooks (embeds)                    │  │
│  │  8. Update state.json                                 │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    ┌─────────┐   ┌──────────┐   ┌──────────┐
    │ Discord │   │  SIP     │   │ state.   │
    │ Webhook │   │  Elfak   │   │ json     │
    └─────────┘   └──────────┘   └──────────┘
                                       │
                                       ▼
                               ┌──────────────┐
                               │  Git Commit  │
                               │  & Push      │
                               └──────────────┘
```

## 🔧 Component Details

### 1. **watcher.py** (Main Scraper)

**Dependencies:**

- `httpx`: Async HTTP client with HTTP/2 support
- `selectolax`: Fast HTML parser (Rust-based, uses Modest engine)

**Key Functions:**

| Function                             | Purpose                                    | Performance            |
| ------------------------------------ | ------------------------------------------ | ---------------------- |
| `fetch_page()`                       | Async page fetching with retries           | ~100-300ms per page    |
| `extract_article_urls()`             | Extract all /article/ links from list page | ~5-10ms per page       |
| `parse_article_page()`               | Parse full article (title, date, content)  | ~200-400ms per article |
| `parse_serbian_date()`               | Parse Serbian date format with time        | <1ms                   |
| `is_article_recent()`                | Filter articles by CUTOFF_DATE             | <1ms                   |
| `normalize_content_from_container()` | Extract formatted content with Markdown    | ~10-20ms per article   |
| `send_discord_message()`             | Send rich embed to Discord webhook         | ~50-150ms per webhook  |

**Flow (Two-Phase Architecture):**

```
Phase 1: Collect URLs
1. Load state ──→ 2. Fetch all 15 category pages ──→ 3. Extract article URLs
                   (async parallel)                        ↓
                                                     4. Group by category
                                                            ↓
                                                     5. Find new URLs

Phase 2: Parse & Send
6. For each new URL:
   ├─ Fetch full article page
   ├─ Parse title, date, content, image
   ├─ Parse Serbian date (including time)
   └─ Filter by CUTOFF_DATE (Dec 1, 2025)
        ↓
7. Deduplicate by title + content
   (not just URL)
        ↓
8. Sort by publication date
   (oldest first)
        ↓
9. Send to Discord in chronological order
   ├─ Rich embeds with Markdown
   ├─ Accurate timestamp from article
   ├─ Bot name: "Elfak SIP"
   └─ Avatar: Elfak logo (if available)
        ↓
10. Update state.json
```

### 2. **Article Extraction Strategy**

The scraper uses a **multi-level fallback** approach:

```python
1. Find all <a href="/article/...">
   ↓
2. Attempt to extract title:
   ├─ Check link text (not "Opširnije")
   ├─ Search parent for <h1>-<h6>
   ├─ Look for class*="title" or class*="naslov"
   ├─ Traverse up DOM tree for headings
   └─ Fallback: Use URL slug
   ↓
3. Create Article object with URL (unique key)
```

This handles various HTML structures on the site.

### 3. **Date Extraction & Filtering**

**Serbian Date Parsing:**

- Format: `"Пон, 24. Нов, 2025. у 13:52"`
- Extracts: day, month (Cyrillic), year, hour, minute
- Timezone: UTC
- Returns: `datetime` object

**Date Filtering:**

```python
CUTOFF_DATE = datetime(2025, 12, 1, tzinfo=timezone.utc)

# Only articles after Dec 1, 2025 are posted to Discord
if article_date < CUTOFF_DATE:
    skip article
```

**Supported Month Names:**

| Serbian   | Short | Number |
| --------- | ----- | ------ |
| јануар    | јан   | 1      |
| фебруар   | феб   | 2      |
| март      | мар   | 3      |
| април     | апр   | 4      |
| мај       | мај   | 5      |
| јун       | јун   | 6      |
| јул       | јул   | 7      |
| август    | авг   | 8      |
| септембар | сеп   | 9      |
| октобар   | окт   | 10     |
| новембар  | нов   | 11     |
| децембар  | дец   | 12     |

### 4. **Deduplication Strategy**

**Two-level deduplication:**

1. **URL-based** (state.json):

   ```python
   if url in seen_urls:
       skip
   ```

2. **Content-based** (before posting):
   ```python
   content_hash = (title.lower(), content[:500].lower())
   if content_hash in seen_content:
       skip duplicate
   ```

This prevents posting:

- Same article re-posted under different URL
- Duplicate announcements with identical content
- Cross-posted articles from different categories

### 5. **Chronological Sorting**

Before sending to Discord, all articles are sorted by publication date:

```python
articles.sort(key=lambda a: parse_serbian_date(a.date))
```

**Why oldest-first?**

- More natural reading order
- Historical context preserved
- Better for following multi-day announcements

**Two-phase approach:**

```
Phase 1: List Page
├─ Try to extract from card/listing
└─ If not found → Phase 2

Phase 2: Article Page (lazy fetch)
├─ Check meta tags: article:published_time
├─ Check <time> tags with datetime attribute
├─ Search for class*="date", class*="datum"
└─ Fallback: null (date not shown in embed)
```

**Rate Limiting:**

- Sleep 0.7s between article page fetches
- Prevents overwhelming the server
- Complies with polite scraping guidelines

### 6. **State Management**

**state.json structure:**

```json
{
  "seen_urls": [
    "https://sip.elfak.ni.ac.rs/article/12345",
    "https://sip.elfak.ni.ac.rs/article/12346",
    ...
  ],
  "last_checked": "2026-01-04T10:15:00.000Z"
}
```

**Operations:**

- **Load**: `O(n)` - read JSON, convert to set
- **Check**: `O(1)` - set membership test
- **Update**: `O(n)` - add new URLs to set
- **Save**: `O(n)` - write JSON with sorted list (for clean diffs)

**Important:** URLs are tracked even if article is skipped (e.g., duplicate content or old date)

### 7. **Discord Integration**

**Webhook Payload:**

```json
{
  "embeds": [
    {
      "author": {
        "name": "SIP Elfak",
        "url": "https://sip.elfak.ni.ac.rs"
      },
      "title": "Article title (max 256 chars)",
      "url": "https://...",
      "description": "Full article content with Markdown formatting",
      "fields": [
        {
          "name": "📅 Објављено",
          "value": "Сре, 31. Дец, 2025. у 12:48",
          "inline": true
        },
        {
          "name": "📂 Категорија",
          "value": "Остало",
          "inline": true
        }
      ],
      "color": 43263, // #0099FF (brighter blue)
      "timestamp": "2025-12-31T12:48:00+00:00", // Actual article date/time
      "thumbnail": { "url": "https://..." }, // Or "image" for image-only posts
      "footer": { "text": "SIP Elfak Bot" }
    }
  ],
  "username": "Elfak SIP",
  "avatar_url": "https://sip.elfak.ni.ac.rs/images/logos/logo.svg"
}
```

**Key Features:**

- **Timestamp**: Uses actual article publication date/time (not current time)
- **Content**: Full article with Markdown ([links], **bold**, bullet lists)
- **Images**: Thumbnail for text posts, full image for image-only posts
- **Bot Identity**: Custom name and avatar
- **Fields**: Category and date shown separately for clarity
  "username": "SIP Elfak Notifier"
  }

````

**Rate Limits:**

- Discord: 30 req/min per webhook
- Bot: 2.0s sleep between sends (DISCORD_SEND_DELAY)
- Bot: 0.5s sleep between fetches (RATE_LIMIT_SLEEP)
- Typical: 1-10 articles per run
- **Well within limits** ✅

**Error Handling:**

- Automatic retry on 429 (rate limit) with exponential backoff
- Detailed error messages with status codes
- Continues processing even if one webhook fails
- **Well within limits** ✅

### 8. **GitHub Actions Workflow**

**Trigger:**

```yaml
schedule:
  - cron: "0 16 * * *" # Daily at 16:00 UTC
workflow_dispatch: # Manual trigger
````

**Steps:**

1. **Checkout** → Clone repo
2. **Setup Python** → Install 3.11 + cache pip
3. **Install deps** → `pip install -r requirements.txt`
4. **Run scraper** → Execute with `DISCORD_WEBHOOK` secret
5. **Commit state** → Push `state.json` back to repo

**Git Config:**

```bash
user.email: github-actions[bot]@users.noreply.github.com
user.name: github-actions[bot]
commit message: 🤖 Update state.json [skip ci]
```

**[skip ci]** prevents infinite loop (workflow won't re-trigger on its own commits)

## ⚡ Performance Benchmarks

## ⚡ Performance Benchmarks

| Operation                       | Time        | Notes                   |
| ------------------------------- | ----------- | ----------------------- |
| Full scrape (15 category pages) | 1-3s        | Parallel async          |
| Parse 1 page                    | 5-10ms      | selectolax is fast      |
| Fetch 1 article                 | 200-400ms   | Full content extraction |
| Parse Serbian date              | <1ms        | Regex-based             |
| Send 1 Discord embed            | 50-150ms    | Webhook POST            |
| **Total run (no new articles)** | **~2-5s**   | ✅                      |
| **Total run (10 new articles)** | **~30-50s** | ✅ (includes sorting)   |
| **Daily run (typical)**         | **~10-20s** | ✅ (1-5 new articles)   |

## 🔒 Security Considerations

1. **Secrets Management**

   - `DISCORD_WEBHOOK` stored in GitHub Secrets
   - Never logged or exposed in Actions output
   - Environment variable only (not in code)

2. **Web Scraping Ethics**

   - User-Agent set: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
   - Rate limiting: 0.5s between article fetches, 2.0s between Discord posts
   - Respects server resources
   - Public academic site (no auth bypass)
   - Date filtering reduces unnecessary fetches
   - Rate limiting: 0.7s between requests
   - Respects server resources
   - Public academic site (no auth bypass)

3. **Error Handling**
   - Retries with exponential backoff on network errors
   - Automatic retry on Discord 429 (rate limit) errors
   - Graceful degradation (skip articles if parse fails)
   - Never crashes on parse errors
   - Detailed error logging with status codes

## 📊 Scalability

**Current capacity:**

- Monitors: 15 SIP categories
- Typical: 200-250 article URLs tracked
- Daily new: 5-15 articles (after date filtering)
- Growth potential: Can handle 1000+ articles in state.json

**To scale further:**

- Add more categories to `LIST_PAGES` list
- Adjust `CUTOFF_DATE` if needed
- Adjust schedule (currently daily at 16:00 UTC)
- Consider database instead of JSON (for 10,000+ articles)

## 🧪 Testing Strategy

**Local testing:**

```bash
export DISCORD_WEBHOOK="..."
python watcher.py
```

**GitHub Actions testing:**

- Use `workflow_dispatch` for manual runs
- Check logs in Actions tab
- Verify `state.json` commits

**Validation:**

- ✅ No syntax errors (py_compile)
- ✅ Dependencies pinned (requirements.txt)
- ✅ Error handling on all I/O
- ✅ Graceful first-run handling
- ✅ Deduplication tested

## 🔮 Future Enhancements

Potential improvements:

1. **Multi-channel support**

   - Different webhooks for different sections
   - Priority channels for "Važna obaveštenja"

2. **Rich article previews**

   - Extract first paragraph as description
   - Add thumbnail images

3. **Advanced filtering**

   - Keyword-based routing
   - Student year filtering

4. **Analytics**

   - Track posting frequency
   - Most active sections
   - Response time metrics

5. **Database backend**
   - PostgreSQL/SQLite for 1000+ articles
   - Query historical posts
   - Better state management

## 📦 Dependencies

| Package      | Version | Size   | Purpose            |
| ------------ | ------- | ------ | ------------------ |
| `httpx`      | 0.27.2  | ~500KB | Async HTTP client  |
| `selectolax` | 0.3.24  | ~1MB   | HTML parser (Rust) |

**Total install size:** ~1.5-2MB (extremely lightweight!)

## 🎯 Design Decisions

**Why httpx over requests?**

- Async support → parallel fetching
- HTTP/2 support → faster
- Modern API → better error handling

**Why selectolax over BeautifulSoup?**

- 5-25x faster (Rust + Modest engine)
- Lower memory usage
- CSS selectors built-in

**Why JSON over database?**

- Simplicity (single file)
- Git-friendly (trackable changes)
- No external dependencies
- Sufficient for <1000 articles

**Why GitHub Actions over external cron?**

- Free for public repos
- Built-in secrets management
- Version control integration
- Easy debugging (logs)

---

Built with ❤️ for speed and reliability.
