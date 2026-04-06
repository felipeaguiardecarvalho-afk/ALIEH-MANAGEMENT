"""Shim: SQL em :mod:`database.repositories.sku_codec_repository`."""

from __future__ import annotations

from database.repositories.sku_codec_repository import (
    _next_sku_sequence,
    build_product_sku_body,
    format_sku_sequence_int,
    sku_base_body_after_seq,
    sku_base_body_exists,
    sku_color_segment_two_chars,
    sku_segment_two_chars,
    sync_sku_sequence_counter_from_skus,
)

__all__ = [
    "_next_sku_sequence",
    "build_product_sku_body",
    "format_sku_sequence_int",
    "sku_base_body_after_seq",
    "sku_base_body_exists",
    "sku_color_segment_two_chars",
    "sku_segment_two_chars",
    "sync_sku_sequence_counter_from_skus",
]
