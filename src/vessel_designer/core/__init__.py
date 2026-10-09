"""Vessel calculation core, ported from the Ankobra feasibility engine (ADR 0002).

This package is the single master of the vessel code (ADR 0004). Pure calculation: no I/O,
no drawing. Some defaults from the original project (e.g. Cb 0.85, a 28 m tank-length cap)
are still baked in and are being turned into inputs (see ROADMAP.md).
"""
