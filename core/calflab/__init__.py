"""CALFLAB core: headless domain logic for calf-robot co-design.

Nothing in this package may import web, server or UI code. Clients (web app,
Rhino, Blender, CLI, notebooks) reach the core only through ``calflab_server``
or by importing this package directly.
"""

import warnings

# `cma` warns at import that matplotlib is missing; CALFLAB never uses cma's plotting.
warnings.filterwarnings("ignore", message="Could not import matplotlib")

__version__ = "0.1.0"

# Bump when node/plugin semantics change in a way that must invalidate caches.
CODE_VERSION = "1"
