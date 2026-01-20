import feedparser
import logging
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from time import mktime

logger = logging.getLogger(__name__)

def load_feeds_config() -> List[Dict[str, str]]:
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'feeds.json')
    
    try:
        with open(config_path, 'r') as f:
            feeds = json.load(f)
            logger.info(f"Loaded {len(feeds)} feed configurations")
            return feeds
    except FileNotFoundError:
        logger.error(f"Feeds config not found at {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in feeds config: {e}")
        raise

def parse_published_date(entry: Dict) -> Optional[datetime]:
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            return datetime.fromtimestamp(mktime(entry.published_parsed))
        except (ValueError, OverflowError):
            pass
    
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        try:
            return datetime.fromtimestamp(mktime(entry.updated_parsed))
        except (ValueError, OverflowError):
            pass
    
    return None

def extract_raw_text(entry: Dict) -> Optional[str]:
    if hasattr(entry, 'summary') and entry.summary:
        return entry.summary[:2000]
    
    if hasattr(entry, 'description') and entry.description:
        return entry.description[:2000]
    
    if hasattr(entry, 'content') and entry.content:
        for content in entry.content:
            if 'value' in content:
                return content['value'][:2000]
    
    return None

def fetch_feed(feed_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_name = feed_config.get('source_name', 'Unknown')
    feed_url = feed_config.get('feed_url')
    category_hint = feed_config.get('category_hint')
    signal_type = feed_config.get('signal_type')
    weight = feed_config.get('weight', 0.5)
    region_hint = feed_config.get('region_hint')
    
    if not feed_url:
        logger.error(f"No feed_url for source: {source_name}")
        return []
    
    logger.info(f"Fetching feed: {source_name} (weight={weight}) from {feed_url}")
    
    try:
        user_agent = os.environ.get('INGESTION_USER_AGENT', 
                                     'EnergyRiskIQ/1.0 (+https://energyriskiq.com)')
        
        import socket
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(15)
        try:
            feed = feedparser.parse(feed_url, agent=user_agent)
        finally:
            socket.setdefaulttimeout(old_timeout)
        
        if feed.bozo and feed.bozo_exception:
            logger.warning(f"Feed parsing warning for {source_name}: {feed.bozo_exception}")
        
        if not feed.entries:
            logger.warning(f"No entries found in feed: {source_name}")
            return []
        
        events = []
        for entry in feed.entries:
            title = getattr(entry, 'title', None)
            link = getattr(entry, 'link', None)
            
            if not title or not link:
                logger.debug(f"Skipping entry without title or link in {source_name}")
                continue
            
            event = {
                'title': title.strip(),
                'source_name': source_name,
                'source_url': link,
                'event_time': parse_published_date(entry),
                'raw_text': extract_raw_text(entry),
                'category_hint': category_hint,
                'signal_type': signal_type,
                'weight': weight,
                'region_hint': region_hint
            }
            events.append(event)
        
        logger.info(f"Fetched {len(events)} events from {source_name}")
        return events
    
    except Exception as e:
        logger.error(f"Error fetching feed {source_name}: {e}")
        return []

def fetch_all_feeds() -> List[Dict[str, Any]]:
    feeds_config = load_feeds_config()
    all_events = []
    
    for feed_config in feeds_config:
        try:
            events = fetch_feed(feed_config)
            all_events.extend(events)
        except Exception as e:
            logger.error(f"Failed to process feed {feed_config.get('source_name')}: {e}")
            continue
    
    logger.info(f"Total events fetched from all feeds: {len(all_events)}")
    return all_events
