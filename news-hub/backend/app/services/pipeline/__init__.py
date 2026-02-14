"""
Pipeline Services Package

Provides news processing and storage functionality.
"""

from app.services.pipeline.processor import (
    NewsPipeline,
    CollectionService,
)


__all__ = [
    "NewsPipeline",
    "CollectionService",
]
