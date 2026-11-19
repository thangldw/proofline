"""Single call-time seam for building the configured generation provider.

Route modules call ``provider_runtime.build_generation_provider`` so tests (and embedders) can
replace the provider in one place regardless of which router handles the request.
"""

from __future__ import annotations

from . import model_gateway
from .config import Settings


def build_generation_provider(settings: Settings) -> model_gateway.GenerationProvider | None:
    return model_gateway.build_generation_provider(settings)
