import os
from fastapi import Depends

from llm.adapters.gemini import GeminiAdapter
from llm.adapters.openai import OpenAIAdapter
from llm.router import LLMRouter
from llm.registry import DEFAULT_REGISTRY

from strategies.v2 import V2Strategy
from strategies.fb import FBStrategy
from strategies.atelier import AtelierStrategy
from search.web import WebImageSearch
from search.noop import NoOpSearch
from postprocessors.compositor import RERACompositor
from postprocessors.aspect_ratio_fill import AspectRatioFillProcessor
from serializers.mongo_s3 import MongoS3Serializer

_router = None
_strategies = {}
_searches = {}
_post_processors = {}
_serializer = None

def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        models = {
            "gemini": GeminiAdapter(os.getenv("GEMINI_API_KEY", "")),
            "openai": OpenAIAdapter(os.getenv("OPENAI_API_KEY", "")),
        }
        _router = LLMRouter(models=models, registry=DEFAULT_REGISTRY)
    return _router


def get_strategies() -> dict:
    global _strategies
    if not _strategies:
        _strategies = {
            "v2": V2Strategy(),
            "fb": FBStrategy(),
            "atelier": AtelierStrategy(),
        }
    return _strategies


def get_searches() -> dict:
    global _searches
    if not _searches:
        _searches = {
            "web": WebImageSearch(),
            "none": NoOpSearch(),
        }
    return _searches


def get_post_processors() -> dict:
    global _post_processors
    if not _post_processors:
        _post_processors = {
            "aspect_ratio_fill": AspectRatioFillProcessor(),
            "compositor": RERACompositor(),
        }
    return _post_processors


def get_serializer() -> MongoS3Serializer:
    global _serializer
    if _serializer is None:
        _serializer = MongoS3Serializer()
    return _serializer
