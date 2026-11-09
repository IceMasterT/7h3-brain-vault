"""brainlib: the shared core of the second brain.

Every reader of the vault (Claude Code hooks, the MCP server, Hermes Agent
hooks, the brain CLI and the local-model chat loop) goes through this package,
so search, validation and safety rules behave the same for every AI.

Standard library only. Python 3.9+.
"""

__version__ = "2.0.0"
