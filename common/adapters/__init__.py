# common/adapters/__init__.py
# Adapters pour chaque plateforme - utilisent le Common Core

from common.adapters.fb_adapter import FBAdapter, generate_post as fb_generate
from common.adapters.li_adapter import LIAdapter, generate_post as li_generate
from common.adapters.tw_adapter import TWAdapter, generate_tweet as tw_generate

__all__ = [
    "FBAdapter",
    "LIAdapter", 
    "TWAdapter",
    "fb_generate",
    "li_generate", 
    "tw_generate",
]