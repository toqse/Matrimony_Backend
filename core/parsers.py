"""
Allow JSON body when client sends Content-Type: text/plain (e.g. Postman with "Text" selected).
"""
from rest_framework.parsers import JSONParser


class PlainTextJSONParser(JSONParser):
    """Parse JSON from request body when Content-Type is text/plain."""
    media_type = 'text/plain'
