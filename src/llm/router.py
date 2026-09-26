"""Multi-Provider Model Router & 3-Tier Execution Engine.

Routes tasks to optimal models based on complexity tiers (Fast, Balanced, Reasoning),
cost profiles, and handles graceful cross-provider fallback chains.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class ModelTier(str, Enum):
    TIER_1_FAST = "tier_1_fast"          # Light transforms, parsing, quick classification
    TIER_2_BALANCED = "tier_2_balanced"  # Standard conversational Q&A, summarization
    TIER_3_REASONING = "tier_3_reasoning"# Complex coding, architecture, deep multi-step logic


class ModelProvider(str, Enum):
    NVIDIA = "nvidia"
    OPENAI = "openai"
    GROQ = "groq"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


@dataclass
class ModelConfig:
    provider: ModelProvider
    model_name: str
    tier: ModelTier
    cost_per_1k_input: float
    cost_per_1k_output: float
    max_context_tokens: int = 8192


class ModelRouter:
    """Intelligent model selection and fallback management."""

    DEFAULT_CATALOG: dict[str, ModelConfig] = {
        "fast_nvidia": ModelConfig(
            provider=ModelProvider.NVIDIA,
            model_name="meta/llama-3.1-8b-instruct",
            tier=ModelTier.TIER_1_FAST,
            cost_per_1k_input=0.0002,
            cost_per_1k_output=0.0002,
        ),
        "balanced_nvidia": ModelConfig(
            provider=ModelProvider.NVIDIA,
            model_name="meta/llama-3.1-70b-instruct",
            tier=ModelTier.TIER_2_BALANCED,
            cost_per_1k_input=0.0007,
            cost_per_1k_output=0.0009,
        ),
        "reasoning_nvidia": ModelConfig(
            provider=ModelProvider.NVIDIA,
            model_name="nvidia/nemotron-4-340b-instruct",
            tier=ModelTier.TIER_3_REASONING,
            cost_per_1k_input=0.0020,
            cost_per_1k_output=0.0040,
        ),
        "local_ollama": ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_name="llama3:latest",
            tier=ModelTier.TIER_2_BALANCED,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        ),
    }

    def __init__(self, default_provider: ModelProvider = ModelProvider.NVIDIA):
        self.default_provider = default_provider
        self.catalog = dict(self.DEFAULT_CATALOG)

    def classify_task_tier(self, task_prompt: str) -> ModelTier:
        """Classify task complexity into appropriate tier."""
        text = task_prompt.lower()
        length = len(task_prompt.split())

        # High complexity keywords
        reasoning_words = [
            "architect", "refactor", "security audit", "vulnerability",
            "optimize algorithm", "multi-agent", "distributed", "concurrency",
            "proof", "deep analysis", "tradeoff", "system design"
        ]
        if any(rw in text for rw in reasoning_words) or length > 500:
            return ModelTier.TIER_3_REASONING

        # Fast tier criteria
        fast_words = ["translate", "reformat", "extract email", "summarize in 3 bullet", "clean up", "lowercase"]
        if (any(fw in text for fw in fast_words) and length < 60) or length < 15:
            return ModelTier.TIER_1_FAST

        return ModelTier.TIER_2_BALANCED

    def select_model(
        self,
        task_prompt: str,
        preferred_tier: Optional[ModelTier] = None,
        prefer_local: bool = False,
    ) -> dict[str, Any]:
        """Select optimal model and provider fallback chain."""
        tier = preferred_tier or self.classify_task_tier(task_prompt)

        if prefer_local:
            return {
                "selected_model": "llama3:latest",
                "provider": ModelProvider.OLLAMA.value,
                "tier": tier.value,
                "fallback_chain": ["meta/llama-3.1-8b-instruct"],
                "reason": "Local inference preferred.",
            }

        if tier == ModelTier.TIER_1_FAST:
            primary = self.catalog["fast_nvidia"]
            fallback = ["meta/llama-3.1-70b-instruct", "llama3:latest"]
        elif tier == ModelTier.TIER_3_REASONING:
            primary = self.catalog["reasoning_nvidia"]
            fallback = ["meta/llama-3.1-70b-instruct", "meta/llama-3.1-8b-instruct"]
        else:
            primary = self.catalog["balanced_nvidia"]
            fallback = ["meta/llama-3.1-8b-instruct", "llama3:latest"]

        return {
            "selected_model": primary.model_name,
            "provider": primary.provider.value,
            "tier": tier.value,
            "estimated_cost_per_1k": primary.cost_per_1k_input,
            "fallback_chain": fallback,
            "reason": f"Classified as {tier.value} based on prompt complexity.",
        }


model_router = ModelRouter()
