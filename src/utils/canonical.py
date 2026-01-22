"""
Canonical URL Builder Utility

Ensures all pages output consistent canonical URLs with:
- Host: https://energyriskiq.com (no www, always https)
- Path: current request path
- Query: strips tracking params (utm_*, gclid, fbclid)
"""
import os
from urllib.parse import urlencode, parse_qs

CANONICAL_HOST = "https://energyriskiq.com"

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'gclid', 'fbclid', 'ref', 'source'
}


def build_canonical_url(path: str, query_string: str = None) -> str:
    """
    Build a canonical URL for the given path.
    
    Args:
        path: The request path (e.g., "/marketing/samples")
        query_string: Optional query string to filter
        
    Returns:
        Canonical URL starting with https://energyriskiq.com
    """
    if not path:
        path = "/"
    
    if not path.startswith("/"):
        path = "/" + path
    
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    
    if query_string:
        params = parse_qs(query_string, keep_blank_values=False)
        filtered = {
            k: v for k, v in params.items()
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith('utm_')
        }
        if filtered:
            clean_params = {k: v[0] if len(v) == 1 else v for k, v in filtered.items()}
            query = "?" + urlencode(clean_params, doseq=True)
        else:
            query = ""
    else:
        query = ""
    
    return f"{CANONICAL_HOST}{path}{query}"


def get_canonical_tag(path: str, query_string: str = None) -> str:
    """
    Get the full canonical link tag HTML.
    
    Args:
        path: The request path
        query_string: Optional query string
        
    Returns:
        HTML link tag string
    """
    url = build_canonical_url(path, query_string)
    return f'<link rel="canonical" href="{url}">'
