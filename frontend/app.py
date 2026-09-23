"""FastAPI entrypoint for frontend server. Alias/wrapper for main.py.
"""
from frontend.main import app, chat, _get_card

__all__ = ["app", "chat", "_get_card"]

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
