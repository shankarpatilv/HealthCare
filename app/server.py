import uvicorn

from app.config import config

if __name__ == "__main__":
    print(f"API listening on http://localhost:{config.port}")
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.port, reload=config.env == "development")
