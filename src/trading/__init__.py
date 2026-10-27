"""Execution side: ledger, risk gates, order executor, reconciliation.

Real-order capability is gated by config.trading_mode; the default
research-only mode keeps every path in this package inert.
"""
