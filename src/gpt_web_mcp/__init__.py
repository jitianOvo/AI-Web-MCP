"""Compatibility namespace; implementation lives in ai_web_mcp."""
from importlib import import_module
import sys
from ai_web_mcp import __version__, PROTOCOL_VERSION
for _name in ('config', 'protocol', 'providers', 'targets', 'storage', 'client'):
    sys.modules[__name__ + '.' + _name] = import_module('ai_web_mcp.' + _name)
