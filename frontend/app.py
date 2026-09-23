"""FastAPI entrypoint for frontend server. Alias/wrapper for main.py.
"""
import os
import sys

# Ensure current directory is in sys.path for robust module resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from main import app, chat, _get_card
except ImportError:
    from frontend.main import app, chat, _get_card

__all__ = ["app", "chat", "_get_card"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
