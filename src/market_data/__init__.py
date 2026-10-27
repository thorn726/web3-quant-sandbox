"""Market data pipeline: bronze (raw archive) → silver (cleaned bars) → gold (features).

Read-only for consumers; owned by the ingest tasks. See
.scratch/trading-data-platform/spec.md for the layering contract.
"""
