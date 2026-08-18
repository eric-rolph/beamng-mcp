"""Shared toolkit for the Giant Props pack examples.

Each mod folder under ``examples/giant_props`` owns a deterministic Blender
generator, a ``spec.py`` with the mod's authored constants, and thin build
wrappers around this library. The library keeps the Cannon Car Wash evidence
chain: Blender owns every coordinate, the handoff JSON is the single source of
physics truth, and generated runtime files are never hand-patched.
"""
