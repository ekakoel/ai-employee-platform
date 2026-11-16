"""Fail-closed authorization for knowledge source retrieval.

Policy administration is deliberately separate from retrieval. Sources without an
approved KnowledgeSourcePolicy are not visible to model context.
"""
from app.knowledge.retrieval import authorized_source_ids

__all__ = ["authorized_source_ids"]
