# Example Discord Embed Output

When a new article is detected, the bot sends a Discord embed like this:

```
┌─────────────────────────────────────────────────────────┐
│ 🔵 SIP Elfak Notifier                                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ **Važno obaveštenje za studente**                       │
│ (Clickable link to full article)                        │
│                                                          │
│ 📅 **Datum:** 04.01.2026                                │
│ 📌 **Izvor:** SIP – Naslovna                            │
│                                                          │
│ ───────────────────────────────────────────────────     │
│ SIP Elfak Bot · Today at 10:15 AM                       │
└─────────────────────────────────────────────────────────┘
```

## Embed Structure

- **Color**: Blue (#00A8E8)
- **Title**: Article title (max 256 chars)
- **URL**: Direct link to the article
- **Description**: Contains:
  - Date (if available from article page)
  - Source section name
- **Timestamp**: ISO 8601 format (Discord auto-converts to user's timezone)
- **Footer**: "SIP Elfak Bot"
- **Username**: "SIP Elfak Notifier"

## Example JSON Payload

```json
{
  "embeds": [
    {
      "title": "Važno obaveštenje za studente",
      "url": "https://sip.elfak.ni.ac.rs/article/12345",
      "description": "📅 **Datum:** 04.01.2026\n📌 **Izvor:** SIP – Naslovna",
      "color": 43752,
      "timestamp": "2026-01-04T10:15:00.000Z",
      "footer": {
        "text": "SIP Elfak Bot"
      }
    }
  ],
  "username": "SIP Elfak Notifier"
}
```

## Rate Limiting

- Discord allows up to 30 requests per minute per webhook
- The bot sleeps 0.5s between notifications
- Typical batch: 1-5 new articles every 15 minutes
- Well within safe limits
