from __future__ import annotations

import logging
from typing import Callable, Awaitable, Any

from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from llm.base import BaseLLM, LLMRequest, LLMResponse, ImageResponse, ProviderTransientError, ProviderPermanentError
from llm.registry import DEFAULT_REGISTRY
from core.observability import trace, histogram, increment

logger = logging.getLogger("revCreate.llm.router")


class LLMRouter:
    def __init__(
        self,
        models: dict[str, BaseLLM],
        registry: dict[str, str] | None = None,
    ) -> None:
        self.models = models
        self.registry = registry if registry is not None else DEFAULT_REGISTRY

    async def route(self, request: LLMRequest) -> LLMResponse:
        model_name = self.registry[request.task_type]
        model = self.models[model_name]
        fallback_triggered = False
        with trace("llm.route", resource=request.task_type,
                   **{"llm.provider": model_name, "llm.task_type": request.task_type}):
            try:
                result = await self._with_retry(lambda: model.generate(request), request.task_type, model_name)
            except ProviderTransientError:
                fallback_name = self._fallback(model_name)
                logger.warning(
                    "Fallback triggered: model=%s failed for task_type=%s, using %s",
                    model_name, request.task_type, fallback_name,
                )
                increment("llm.fallback", tags=[f"task_type:{request.task_type}", f"failed_model:{model_name}"])
                fallback_triggered = True
                fallback_model = self.models[fallback_name]
                result = await self._with_retry(lambda: fallback_model.generate(request), request.task_type, fallback_name)
            histogram("llm.latency", result.latency_ms,
                      tags=[f"task_type:{request.task_type}", f"model:{result.model}"])
            return result

    async def route_image(self, request: LLMRequest) -> ImageResponse:
        model_name = self.registry[request.task_type]
        model = self.models[model_name]
        with trace("llm.route", resource=request.task_type,
                   **{"llm.provider": model_name, "llm.task_type": request.task_type}):
            try:
                result = await self._with_retry(lambda: model.generate_image(request), request.task_type, model_name)
            except (ProviderTransientError, ProviderPermanentError) as exc:
                fallback_name = self._fallback(model_name)
                logger.warning(
                    "Fallback triggered: model=%s failed for task_type=%s (%s), using %s",
                    model_name, request.task_type, type(exc).__name__, fallback_name,
                )
                increment("llm.fallback", tags=[f"task_type:{request.task_type}", f"failed_model:{model_name}"])
                fallback_model = self.models[fallback_name]
                result = await self._with_retry(lambda: fallback_model.generate_image(request), request.task_type, fallback_name)
            histogram("llm.latency", result.latency_ms,
                      tags=[f"task_type:{request.task_type}", f"model:{result.model}"])
            return result

    async def _with_retry(self, fn: Callable[[], Awaitable[Any]], task_type: str = "", model_name: str = "") -> Any:
        attempt_num = 0
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type(ProviderTransientError),
            reraise=True,
        ):
            with attempt:
                attempt_num += 1
                if attempt_num > 1:
                    increment("llm.retry", tags=[f"task_type:{task_type}", f"model:{model_name}", f"attempt:{attempt_num}"])
                return await fn()

    def _fallback(self, failed: str) -> str:
        for name in self.models:
            if name != failed:
                return name
        raise RuntimeError(f"No fallback model available — only model '{failed}' is registered")
