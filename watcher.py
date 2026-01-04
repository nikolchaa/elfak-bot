#!/usr/bin/env python3
"""
SIP Elfak Bot - Strict two-phase scraper with full content extraction
Phase 1: Collect article URLs from list pages
Phase 2: Fetch and parse each article page completely
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser


# Configuration
BASE_URL = "https://sip.elfak.ni.ac.rs"
LIST_PAGES = [
    {"url": "https://sip.elfak.ni.ac.rs/", "category": "Наслovna"},
    {"url": "https://sip.elfak.ni.ac.rs/category/nastava", "category": "Настава"},
    {"url": "https://sip.elfak.ni.ac.rs/category/kalendar", "category": "Календар"},
    {"url": "https://sip.elfak.ni.ac.rs/category/polaganje-ispita", "category": "Полагање испита"},
    {"url": "https://sip.elfak.ni.ac.rs/category/kolokvijumi", "category": "Колоквијуми"},
    {"url": "https://sip.elfak.ni.ac.rs/category/upis-naredne-godine-oas", "category": "Упис наредне године (ОАС)"},
    {"url": "https://sip.elfak.ni.ac.rs/category/mas", "category": "МАС"},
    {"url": "https://sip.elfak.ni.ac.rs/category/das", "category": "ДАС"},
    {"url": "https://sip.elfak.ni.ac.rs/category/obrasci", "category": "Обрасци"},
    {"url": "https://sip.elfak.ni.ac.rs/category/literatura", "category": "Литература"},
    {"url": "https://sip.elfak.ni.ac.rs/category/rezultati", "category": "Резултати"},
    {"url": "https://sip.elfak.ni.ac.rs/category/konkursi", "category": "Конкурси"},
    {"url": "https://sip.elfak.ni.ac.rs/category/ostalo", "category": "Остало"},
    {"url": "https://sip.elfak.ni.ac.rs/category/pomoc", "category": "Помоћ"},
    {"url": "https://sip.elfak.ni.ac.rs/category/kursevi", "category": "Курсеви"},
]
STATE_FILE = Path("state.json")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
RATE_LIMIT_SLEEP = 0.5  # seconds between article fetches
DISCORD_SEND_DELAY = 2.0  # seconds between Discord webhook posts (avoid rate limits)
CUTOFF_DATE = datetime(2025, 12, 1, tzinfo=timezone.utc)  # Only fetch articles after this date
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


# Serbian month name mapping (both full and abbreviated)
SERBIAN_MONTHS = {
    "јануар": 1, "јан": 1,
    "фебруар": 2, "феб": 2,
    "март": 3, "мар": 3,
    "април": 4, "апр": 4,
    "мај": 5,
    "јун": 6,
    "јул": 7,
    "август": 8, "авг": 8,
    "септембар": 9, "сеп": 9,
    "октобар": 10, "окт": 10,
    "новембар": 11, "нов": 11,
    "децембар": 12, "дец": 12,
}


class Article:
    """Represents a fully parsed article"""
    
    def __init__(self, url: str, title: str, date: Optional[str], content: str, image_url: Optional[str] = None, category: Optional[str] = None):
        self.url = url
        self.title = title
        self.date = date
        self.content = content
        self.image_url = image_url
        self.category = category
    
    def __repr__(self):
        return f"Article(url={self.url}, title={self.title[:40]}...)"


def load_state() -> Set[str]:
    """Load seen article URLs from state file"""
    if not STATE_FILE.exists():
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("seen_urls", []))
    except Exception as e:
        print(f"⚠️  Error loading state: {e}")
        return set()


def save_state(seen_urls: Set[str]):
    """Save seen article URLs to state file"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "seen_urls": sorted(list(seen_urls)),
                "last_checked": datetime.now(timezone.utc).isoformat()
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ State saved: {len(seen_urls)} URLs tracked")
    except Exception as e:
        print(f"❌ Error saving state: {e}")


async def fetch_page(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Fetch a page with retries and proper error handling"""
    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=15.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"⚠️  Fetch error (attempt {attempt + 1}/3): {url} - {e}")
            if attempt == 2:
                return None
            await asyncio.sleep(1.5 ** attempt)
    return None


def extract_article_urls(html: str, base_url: str) -> Set[str]:
    """
    Phase 1: Extract ONLY article URLs from list page
    Returns normalized absolute URLs matching /article/ pattern
    """
    urls = set()
    tree = HTMLParser(html)
    
    # Find all links containing /article/
    for link in tree.css("a[href*='/article/']"):
        href = link.attributes.get("href", "")
        if not href or "/article/" not in href:
            continue
        
        # Normalize to absolute URL
        absolute_url = urljoin(base_url, href)
        
        # Validate it's a proper article URL
        parsed = urlparse(absolute_url)
        if "/article/" in parsed.path:
            urls.add(absolute_url)
    
    return urls


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks"""
    # Replace multiple spaces/tabs with single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Replace 3+ newlines with 2 (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def parse_serbian_date(date_string: str) -> Optional[datetime]:
    """
    Parse Serbian date format (e.g., "Пон, 24. Нов, 2025. у 13:52")
    Returns datetime object or None if parsing fails
    """
    if not date_string:
        return None
    
    try:
        # Pattern: day. month_name, year. у hour:minute
        # Examples: "24. Нов, 2025. у 13:52", "Сре, 31. Дец, 2025. у 12:48"
        pattern = r'(\d{1,2})\.\s*([А-Яа-яЁё]+).*?(\d{4})'
        match = re.search(pattern, date_string)
        
        if match:
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year = int(match.group(3))
            
            # Look up month number
            month = SERBIAN_MONTHS.get(month_name)
            
            if month:
                # Try to extract time (hour:minute)
                time_pattern = r'у\s*(\d{1,2}):(\d{2})'
                time_match = re.search(time_pattern, date_string)
                
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                else:
                    # No time specified, use midnight
                    return datetime(year, month, day, tzinfo=timezone.utc)
        
        # Fallback: try to find just the year
        year_match = re.search(r'(\d{4})', date_string)
        if year_match:
            year = int(year_match.group(1))
            # Assume it's recent (current month/day)
            return datetime(year, 1, 1, tzinfo=timezone.utc)
    
    except Exception as e:
        print(f"⚠️  Failed to parse date '{date_string}': {e}")
    
    return None


def is_article_recent(date_string: Optional[str]) -> bool:
    """
    Check if article is after CUTOFF_DATE
    Returns True if date is after cutoff or if date cannot be parsed (assume recent)
    """
    if not date_string:
        # No date available - assume it's recent
        return True
    
    parsed_date = parse_serbian_date(date_string)
    
    if not parsed_date:
        # Couldn't parse - assume it's recent to be safe
        return True
    
    return parsed_date >= CUTOFF_DATE


def extract_date(tree: HTMLParser) -> Optional[str]:
    """
    Extract date from article page
    Looks for dd.mm.yyyy. format or ISO dates
    """
    # Strategy 1: Look for Serbian date format (dd.mm.yyyy.)
    date_pattern = re.compile(r'\b(\d{1,2}\.\s?\d{1,2}\.\s?\d{4}\.?)\b')
    
    # Check meta tags first
    for meta in tree.css("meta[property='article:published_time'], meta[name='date'], meta[itemprop='datePublished']"):
        content = meta.attributes.get("content", "")
        if content:
            return content
    
    # Check time tags
    time_tag = tree.css_first("time")
    if time_tag:
        dt_attr = time_tag.attributes.get("datetime")
        if dt_attr:
            return dt_attr
        time_text = time_tag.text(strip=True)
        if time_text:
            return time_text
    
    # Search in common date containers
    for selector in ["[class*='date']", "[class*='Date']", "[class*='datum']", "[class*='published']"]:
        elem = tree.css_first(selector)
        if elem:
            text = elem.text(strip=True)
            match = date_pattern.search(text)
            if match:
                return match.group(1)
    
    # Last resort: search entire page for date near top
    body_text = tree.body.text() if tree.body else ""
    first_500_chars = body_text[:500]
    match = date_pattern.search(first_500_chars)
    if match:
        return match.group(1)
    
    return None


def convert_table_to_text(table) -> str:
    """Convert HTML table to readable text format"""
    lines = []
    rows = table.css("tr")
    
    for row in rows:
        cells = row.css("td, th")
        if cells:
            cell_texts = [cell.text(strip=True) for cell in cells]
            # Join cells with " | " separator
            lines.append(" | ".join(cell_texts))
    
    return "\n".join(lines) if lines else ""


def normalize_content(tree: HTMLParser) -> str:
    """
    Extract and normalize article content for Discord
    Handles paragraphs, lists, tables, links, and headings
    """
    content_parts = []
    
    # Find main content container
    # Try common article content selectors
    content_container = None
    for selector in [
        "article", 
        "[class*='content']", 
        "[class*='article']",
        "[class*='post']",
        "main",
        ".entry-content"
    ]:
        content_container = tree.css_first(selector)
        if content_container:
            break
    
    # Fallback to body if no content container found
    if not content_container:
        content_container = tree.body
    
    if not content_container:
        return ""
    
    # Remove unwanted elements (navigation, footer, sidebar)
    for unwanted in content_container.css("nav, footer, aside, [class*='sidebar'], [class*='nav'], .comments"):
        unwanted.decompose()
    
    # Process elements in order
    for elem in content_container.iter():
        tag = elem.tag
        
        # Skip if already processed as child
        if not elem.parent:
            continue
        
        # Headings (make bold)
        if tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            text = elem.text(strip=True)
            if text and text.lower() not in ["opširnije", "više", "detaljnije"]:
                content_parts.append(f"\n**{text}**\n")
        
        # Paragraphs
        elif tag == "p":
            text = elem.text(strip=True)
            if text and len(text) > 5:  # Skip empty or very short paragraphs
                content_parts.append(text)
                content_parts.append("\n")
        
        # Lists
        elif tag == "li":
            text = elem.text(strip=True)
            if text:
                content_parts.append(f"• {text}")
                content_parts.append("\n")
        
        # Tables
        elif tag == "table":
            table_text = convert_table_to_text(elem)
            if table_text:
                content_parts.append("\n")
                content_parts.append(table_text)
                content_parts.append("\n")
        
        # Line breaks
        elif tag == "br":
            content_parts.append("\n")
    
    # Join and normalize
    raw_content = "".join(content_parts)
    normalized = normalize_whitespace(raw_content)
    
    return normalized


async def parse_article_page(client: httpx.AsyncClient, url: str, category: str) -> Optional[Article]:
    """
    Phase 2: Fetch and fully parse an article page
    Returns Article with title, date, and normalized content
    """
    html = await fetch_page(client, url)
    if not html:
        print(f"❌ Failed to fetch article: {url}")
        return None
    
    tree = HTMLParser(html)
    
    # Extract title - SIP specific: look for .section-heading h3 first
    title = None
    
    # Try SIP-specific structure first
    section_heading = tree.css_first(".section-heading h3, .section-heading h2, .section-heading h1")
    if section_heading:
        title = section_heading.text(strip=True)
    
    # Fallback to standard h1/h2
    if not title:
        h1 = tree.css_first("h1")
        if h1:
            title = h1.text(strip=True)
    
    if not title:
        h2 = tree.css_first("h2")
        if h2:
            title = h2.text(strip=True)
    
    if not title:
        meta_title = tree.css_first("meta[property='og:title'], meta[name='title']")
        if meta_title:
            title = meta_title.attributes.get("content", "").strip()
    
    if not title:
        title = "Без наслова"
    
    # Extract date - SIP specific: look in col-lg-4 text-right
    date = None
    date_container = tree.css_first(".col-lg-4.text-right, [class*='text-right']")
    if date_container:
        date_text = date_container.text(strip=True)
        if date_text and any(char.isdigit() for char in date_text):
            date = date_text
    
    # Fallback to generic date extraction
    if not date:
        date = extract_date(tree)
    
    # Extract image - look for main content images
    image_url = None
    content_container = tree.css_first(".col-md-9 .col-lg-12, .col-lg-12, .col-md-9")
    if content_container:
        img = content_container.css_first("img")
        if img:
            src = img.attributes.get("src", "")
            if src:
                # Make absolute URL
                if src.startswith("http"):
                    image_url = src
                elif src.startswith("/"):
                    image_url = BASE_URL + src
                else:
                    image_url = urljoin(BASE_URL, src)
    
    # Extract content - SIP specific: look for .col-md-9 or .col-lg-12
    content = None
    
    # Try to find the main content div
    for selector in [".col-md-9 .col-lg-12", ".col-lg-12", ".col-md-9"]:
        content_container = tree.css_first(selector)
        if content_container:
            # Remove heading section if present
            for heading_div in content_container.css(".heading-about, .section-heading"):
                heading_div.decompose()
            
            content = normalize_content_from_container(content_container)
            if content and len(content) > 50:  # Valid content
                break
    
    # Fallback to generic extraction
    if not content or len(content) < 50:
        content = normalize_content(tree)
    
    # If content is still minimal but we have an image, that's okay
    if (not content or len(content) < 50) and not image_url:
        print(f"⚠️  No content or image extracted from: {url}")
        content = "(Садржај није доступан)"
    elif not content or len(content) < 50:
        # We have an image but minimal text
        content = "(Погледајте слику испод)"
    
    return Article(url=url, title=title, date=date, content=content, image_url=image_url, category=category)


def extract_text_with_formatting(elem) -> str:
    """
    Recursively extract text from element preserving formatting:
    - <strong> -> **text**
    - <em> -> *text*
    - <a> -> text (url) or just url
    - Preserve spacing between elements
    """
    result = []
    
    # Process each direct child node
    if hasattr(elem, 'iter'):
        for child in elem.iter():
            if child == elem:
                continue
                
            tag = child.tag
            
            # Get immediate text before processing children
            if tag == "strong" or tag == "b":
                text = child.text(strip=True)
                if text:
                    result.append(f" **{text}** ")
            
            elif tag == "em" or tag == "i":
                text = child.text(strip=True)
                if text:
                    result.append(f" *{text}* ")
            
            elif tag == "a":
                link_text = child.text(strip=True)
                href = child.attributes.get("href", "")
                
                # Skip "Opširnije" and article links
                if link_text.lower() in ["opširnije", "više", "detaljnije", "pročitaj više"]:
                    continue
                if "/article/" in href and not link_text:
                    continue
                
                if href:
                    # Make absolute URL
                    if href.startswith("http"):
                        url = href
                    elif href.startswith("/"):
                        url = BASE_URL + href
                    else:
                        url = urljoin(BASE_URL, href)
                    
                    if link_text:
                        result.append(f" {link_text} ({url}) ")
                    else:
                        result.append(f" {url} ")
                elif link_text:
                    result.append(f" {link_text} ")
            
            elif tag == "br":
                result.append("\n")
            
            elif tag == "p":
                # Will be handled by parent logic
                pass
            
            else:
                # For other inline elements, just get text
                # This catches spans and other containers
                pass
        
        # Now get any remaining text that wasn't in special tags
        # Use a simpler approach: get text node by node
        full_text = elem.text(strip=False) if hasattr(elem, 'text') else ""
        
        # If we didn't extract any formatted content, just return plain text
        if not result:
            return elem.text(strip=True) if hasattr(elem, 'text') else ""
    
    # Join and clean up spacing
    text = "".join(result)
    # Clean up multiple spaces but preserve single spaces
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r' \n ', '\n', text)
    text = re.sub(r'\n ', '\n', text)
    text = re.sub(r' \n', '\n', text)
    
    return text.strip()


def normalize_content_from_container(container) -> str:
    """Extract and normalize content from a specific container element"""
    content_parts = []
    
    # Remove unwanted elements
    for unwanted in container.css("nav, footer, aside, [class*='sidebar'], [class*='nav'], .comments, script, style"):
        unwanted.decompose()
    
    # Process in document order - walk through top-level block elements
    for elem in container.iter():
        # Only process direct block-level children to maintain order
        if elem == container:
            continue
        
        tag = elem.tag
        
        # Skip if this element is nested inside another block element we'll process
        parent = elem.parent
        if parent and parent != container and parent.tag in ["p", "ul", "ol", "div", "table", "h1", "h2", "h3", "h4", "h5", "h6"]:
            continue
        
        # Headings
        if tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            text = elem.text(strip=True)
            if text and text.lower() not in ["opširnije", "više", "detaljnije"]:
                content_parts.append(f"\n**{text}**\n")
        
        # Paragraphs
        elif tag == "p":
            para_text = extract_paragraph_with_formatting(elem)
            if para_text and len(para_text) > 3:
                content_parts.append(para_text)
                content_parts.append("\n\n")
        
        # Unordered/ordered lists
        elif tag in ["ul", "ol"]:
            for li in elem.css("li"):
                li_text = extract_paragraph_with_formatting(li)
                if li_text:
                    content_parts.append(f"• {li_text}\n")
            # Add spacing after list
            content_parts.append("\n")
        
        # Tables
        elif tag == "table":
            # Skip if nested
            if parent and parent.tag == "table":
                continue
            table_text = convert_table_to_text(elem)
            if table_text:
                content_parts.append(f"\n{table_text}\n\n")
    
    # Join and normalize
    raw = "".join(content_parts)
    return normalize_whitespace(raw)


def extract_paragraph_with_formatting(elem) -> str:
    """
    Extract text from paragraph or list item with Markdown formatting
    Handles bold, links, and nested elements
    """
    # Get base text
    para_text = elem.text(strip=False)
    replacements = []  # List of (original_text, markdown_replacement) tuples
    
    # Process links first (they take priority)
    for link in elem.css("a"):
        link_text = link.text(strip=True)
        href = link.attributes.get("href", "")
        
        # Skip "Opširnije" links
        if link_text.lower() in ["opširnije", "više", "detaljnije", "pročitaj više"]:
            para_text = para_text.replace(link_text, "")
            continue
        
        if href and "/article/" not in href:
            # Make absolute URL
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = BASE_URL + href
            else:
                url = urljoin(BASE_URL, href)
            
            # Check if link is inside a strong tag OR contains a strong tag
            parent = link.parent
            is_bold_parent = parent and parent.tag in ["strong", "b"]
            has_bold_child = link.css_first("strong, b") is not None
            
            if link_text:
                if is_bold_parent or has_bold_child:
                    # Bold link: [**text**](url)
                    markdown_link = f"[**{link_text}**]({url})"
                else:
                    # Normal link: [text](url)
                    markdown_link = f"[{link_text}]({url})"
                replacements.append((link_text, markdown_link))
            else:
                # Just URL
                replacements.append((href, url))
    
    # Process strong/bold tags (but skip if already processed as part of link)
    for strong in elem.css("strong, b"):
        strong_text = strong.text(strip=True)
        if not strong_text:
            continue
        
        # Check if this strong contains a link (already handled above)
        has_link = strong.css_first("a") is not None
        
        if not has_link and strong_text:
            # Check if this text was already replaced (part of a link)
            already_replaced = any(strong_text in repl[1] for repl in replacements)
            if not already_replaced:
                replacements.append((strong_text, f"**{strong_text}**"))
    
    # Apply replacements in order (longest first to avoid partial replacements)
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    for original, markdown in replacements:
        # Only replace first occurrence to avoid issues
        para_text = para_text.replace(original, markdown, 1)
    
    # Clean up the text
    para_text = para_text.strip()
    
    # Clean up multiple spaces
    para_text = re.sub(r'  +', ' ', para_text)
    
    return para_text


async def send_discord_message(client: httpx.AsyncClient, article: Article):
    """
    Send article to Discord via webhook
    Uses rich embed formatting with proper structure
    """
    if not DISCORD_WEBHOOK:
        print("⚠️  No Discord webhook configured")
        return
    
    EMBED_DESCRIPTION_LIMIT = 4096
    EMBED_FIELD_VALUE_LIMIT = 1024
    
    embeds = []
    
    # Parse timestamp from article date
    timestamp = None
    if article.date:
        parsed_date = parse_serbian_date(article.date)
        if parsed_date:
            timestamp = parsed_date.isoformat()
        else:
            timestamp = datetime.now(timezone.utc).isoformat()
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
    
    # Build main embed
    if len(article.content) <= EMBED_DESCRIPTION_LIMIT:
        # Single embed with all content
        embed = {
            "author": {
                "name": "SIP Elfak",
                "url": BASE_URL,
            },
            "title": article.title[:256],
            "url": article.url,
            "description": article.content,
            "color": 0x0099FF,  # Brighter blue
            "timestamp": timestamp,
        }
        
        # Add metadata fields (date + category)
        fields = []
        if article.date:
            fields.append({
                "name": "📅 Објављено",
                "value": article.date,
                "inline": True
            })
        if article.category:
            fields.append({
                "name": "📂 Категорија",
                "value": article.category,
                "inline": True
            })
        
        if fields:
            embed["fields"] = fields
        
        # Add image or thumbnail
        if article.image_url:
            # If content is minimal (just image post), use large image
            if len(article.content) < 100:
                embed["image"] = {"url": article.image_url}
            else:
                # Otherwise use thumbnail to save space
                embed["thumbnail"] = {"url": article.image_url}
        
        embed["footer"] = {
            "text": "SIP Elfak Bot"
        }
        
        embeds.append(embed)
    else:
        # Content is too long - split intelligently
        # Strategy: Use description for intro + fields for sections
        
        # Find logical break points (headings with **)
        parts = article.content.split("\n**")
        
        if len(parts) > 1:
            # We have headings - use them as fields
            intro = parts[0].strip()
            
            # First embed with intro
            first_embed = {
                "author": {
                    "name": "SIP Elfak",
                    "url": BASE_URL,
                },
                "title": article.title[:256],
                "url": article.url,
                "description": intro[:EMBED_DESCRIPTION_LIMIT] if intro else "Опширан чланак испод:",
                "color": 0x0099FF,
                "timestamp": timestamp,
            }
            
            # Add metadata fields (date + category)
            fields = []
            if article.date:
                fields.append({
                    "name": "📅 Објављено",
                    "value": article.date,
                    "inline": True
                })
            if article.category:
                fields.append({
                    "name": "📂 Категорија",
                    "value": article.category,
                    "inline": True
                })
            
            if fields:
                first_embed["fields"] = fields
            
            # Add image
            if article.image_url:
                first_embed["thumbnail"] = {"url": article.image_url}
            
            first_embed["footer"] = {"text": "SIP Elfak Bot • 1/..."}
            embeds.append(first_embed)
            
            # Add remaining sections as fields in continuation embeds
            current_fields = []
            
            for i, part in enumerate(parts[1:], start=1):
                # Re-add the ** that was removed by split
                section = "**" + part
                
                # Try to extract heading and content
                lines = section.split("\n", 1)
                if len(lines) == 2:
                    heading = lines[0].strip()
                    content = lines[1].strip()
                else:
                    heading = f"Део {i}"
                    content = section.strip()
                
                # Truncate if too long
                if len(content) > EMBED_FIELD_VALUE_LIMIT:
                    content = content[:EMBED_FIELD_VALUE_LIMIT-20] + "\n\n*(скраћено)*"
                
                current_fields.append({
                    "name": heading[:256],
                    "value": content,
                    "inline": False
                })
                
                # Max 25 fields per embed
                if len(current_fields) >= 25:
                    continuation_embed = {
                        "fields": current_fields,
                        "color": 0x0099FF,
                        "footer": {"text": f"SIP Elfak Bot • {len(embeds)+1}/..."}
                    }
                    embeds.append(continuation_embed)
                    current_fields = []
            
            # Add remaining fields
            if current_fields:
                continuation_embed = {
                    "fields": current_fields,
                    "color": 0x0099FF,
                    "footer": {"text": f"SIP Elfak Bot • {len(embeds)+1}/..."}
                }
                embeds.append(continuation_embed)
        else:
            # No headings - fall back to splitting by paragraphs
            first_chunk = article.content[:EMBED_DESCRIPTION_LIMIT]
            last_newline = first_chunk.rfind('\n\n')
            if last_newline > EMBED_DESCRIPTION_LIMIT // 2:
                first_chunk = article.content[:last_newline]
                remaining = article.content[last_newline:].strip()
            else:
                remaining = article.content[EMBED_DESCRIPTION_LIMIT:].strip()
            
            first_embed = {
                "author": {
                    "name": "SIP Elfak",
                    "url": BASE_URL,
                },
                "title": article.title[:256],
                "url": article.url,
                "description": first_chunk,
                "color": 0x0099FF,
                "timestamp": timestamp,
                "footer": {"text": "SIP Elfak Bot • 1/..."}
            }
            
            # Add metadata fields (date + category)
            fields = []
            if article.date:
                fields.append({
                    "name": "📅 Објављено",
                    "value": article.date,
                    "inline": True
                })
            if article.category:
                fields.append({
                    "name": "📂 Категорија",
                    "value": article.category,
                    "inline": True
                })
            
            if fields:
                first_embed["fields"] = fields
            
            if article.image_url:
                first_embed["thumbnail"] = {"url": article.image_url}
            
            embeds.append(first_embed)
            
            # Split remaining content into field chunks
            paragraphs = remaining.split('\n\n')
            current_field_value = ""
            continuation_fields = []
            field_num = 1
            
            for para in paragraphs:
                if len(current_field_value) + len(para) + 2 <= EMBED_FIELD_VALUE_LIMIT:
                    current_field_value += para + "\n\n"
                else:
                    if current_field_value:
                        continuation_fields.append({
                            "name": f"Наставак {field_num}",
                            "value": current_field_value.strip(),
                            "inline": False
                        })
                        field_num += 1
                    current_field_value = para + "\n\n"
                
                # Create new embed if we hit 25 fields
                if len(continuation_fields) >= 25:
                    continuation_embed = {
                        "fields": continuation_fields,
                        "color": 0x0099FF,
                        "footer": {"text": f"SIP Elfak Bot • {len(embeds)+1}/..."}
                    }
                    embeds.append(continuation_embed)
                    continuation_fields = []
            
            if current_field_value:
                continuation_fields.append({
                    "name": f"Наставак {field_num}",
                    "value": current_field_value.strip(),
                    "inline": False
                })
            
            if continuation_fields:
                continuation_embed = {
                    "fields": continuation_fields,
                    "color": 0x0099FF,
                    "footer": {"text": f"SIP Elfak Bot • {len(embeds)+1}/..."}
                }
                embeds.append(continuation_embed)
    
    # Update footer on last embed
    if len(embeds) > 1:
        embeds[-1]["footer"]["text"] = f"SIP Elfak Bot • {len(embeds)}/{len(embeds)}"
    
    # Send embeds
    try:
        for i, embed in enumerate(embeds):
            payload = {
                "embeds": [embed],
                "username": "Elfak SIP",
                "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_n4cTULTyyibS74QLgtHRRfo6p35NRl1xOp_jlxtqgjYQ=s900-c-k-c0x00ffffff-no-rj"
            }
            
            resp = await client.post(DISCORD_WEBHOOK, json=payload, timeout=10.0)
            
            # Check for rate limit
            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 5)
                print(f"⚠️  Discord rate limit hit! Waiting {retry_after}s...")
                await asyncio.sleep(retry_after)
                # Retry the request
                resp = await client.post(DISCORD_WEBHOOK, json=payload, timeout=10.0)
            
            resp.raise_for_status()
            
            if i == 0:
                print(f"✅ Discord message sent: {article.title[:50]}")
            
            # Rate limit between embeds
            if i < len(embeds) - 1:
                await asyncio.sleep(0.5)
        
    except httpx.HTTPStatusError as e:
        print(f"❌ Discord webhook HTTP error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        print(f"❌ Failed to send Discord message: {e}")


async def main():
    """Main scraper execution"""
    print("🚀 SIP Elfak Bot starting (strict two-phase architecture)...")
    print(f"⏰ Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    if not DISCORD_WEBHOOK:
        print("❌ DISCORD_WEBHOOK environment variable not set!")
        sys.exit(1)
    
    # Load state
    seen_urls = load_state()
    print(f"📋 Loaded state: {len(seen_urls)} URLs already seen")
    
    # Phase 1: Collect article URLs from all list pages
    print("\n📋 PHASE 1: Collecting article URLs...")
    category_urls = {}  # category -> list of URLs
    
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        for source in LIST_PAGES:
            list_url = source["url"]
            category = source["category"]
            print(f"🔍 Scanning: {list_url} ({category})")
            html = await fetch_page(client, list_url)
            if html:
                urls = extract_article_urls(html, BASE_URL)
                print(f"   Found {len(urls)} article URLs")
                
                # Group by category
                if category not in category_urls:
                    category_urls[category] = []
                category_urls[category].extend(urls)
        
        # Count total unique URLs across all categories
        all_urls = set()
        for urls in category_urls.values():
            all_urls.update(urls)
        
        print(f"📊 Total unique article URLs: {len(all_urls)}")
        
        # Find new URLs per category
        urls_to_process = {}  # category -> list of URLs to process
        total_new = 0
        
        for category, urls in category_urls.items():
            # Remove duplicates within category and find new ones
            unique_urls = list(dict.fromkeys(urls))  # Preserve order, remove duplicates
            new_urls_in_category = [url for url in unique_urls if url not in seen_urls]
            
            if new_urls_in_category:
                print(f"   {category}: {len(new_urls_in_category)} new")
                urls_to_process[category] = new_urls_in_category
                total_new += len(new_urls_in_category)
        
        print(f"🆕 Total new articles to process: {total_new}")
        
        if total_new == 0:
            print("✨ No new articles found")
            return
        
        # Phase 2: Fetch and parse each article
        print(f"\n📰 PHASE 2: Parsing {total_new} articles...")
        
        # First, collect all articles
        articles_to_send = []
        processed_count = 0
        
        for category, urls in urls_to_process.items():
            for url in urls:
                processed_count += 1
                print(f"\n[{processed_count}/{total_new}] Processing: {url}")
                print(f"   Category: {category}")
                
                # Parse article page
                article = await parse_article_page(client, url, category)
                
                if not article:
                    print(f"⚠️  Skipping due to parse failure")
                    seen_urls.add(url)
                    continue
                
                print(f"   Title: {article.title[:60]}")
                print(f"   Date: {article.date or 'N/A'}")
                print(f"   Content length: {len(article.content)} chars")
                if article.image_url:
                    print(f"   Image: {article.image_url}")
                
                # Check if article is recent enough
                if not is_article_recent(article.date):
                    print(f"   ⏭️  Skipping - article is older than {CUTOFF_DATE.date()}")
                    seen_urls.add(url)
                    continue
                
                # Add to list for sending
                articles_to_send.append(article)
                
                # Rate limit between fetches
                if processed_count < total_new:
                    await asyncio.sleep(RATE_LIMIT_SLEEP)
        
        # De-duplicate by title and content (not just URL)
        print(f"\n🔍 De-duplicating articles by title and content...")
        seen_content = set()
        unique_articles = []
        for article in articles_to_send:
            content_hash = (article.title.strip().lower(), article.content[:500].strip().lower())
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_articles.append(article)
            else:
                print(f"   ⏭️  Skipping duplicate: {article.title[:60]}")
                seen_urls.add(article.url)  # Still mark as seen
        
        articles_to_send = unique_articles
        
        # Sort articles by date (oldest first)
        print(f"\n📤 Sorting {len(articles_to_send)} articles by date...")
        articles_to_send.sort(key=lambda a: parse_serbian_date(a.date) or datetime.min.replace(tzinfo=timezone.utc))
        
        # Send to Discord in chronological order
        print(f"\n✉️  Sending {len(articles_to_send)} articles to Discord...")
        for i, article in enumerate(articles_to_send, 1):
            print(f"\n[{i}/{len(articles_to_send)}] Sending: {article.title[:60]}")
            await send_discord_message(client, article)
            
            # Mark as seen
            seen_urls.add(article.url)
            
            # Rate limit between Discord webhooks
            if i < len(articles_to_send):
                await asyncio.sleep(DISCORD_SEND_DELAY)
    
    # Save state
    save_state(seen_urls)
    
    print(f"\n✨ Done! Processed {total_new} new articles")
    print(f"📊 Total tracked: {len(seen_urls)} URLs")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
