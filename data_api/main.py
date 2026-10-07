"""
data-api placeholder
Z2 波将实装 FastAPI 应用，包含 E1-E19 端点。
"""


def create_app():
    """Create FastAPI application (placeholder)."""
    try:
        from fastapi import FastAPI
        app = FastAPI(title="观势数据层 API", version="0.1.0-placeholder")

        @app.get("/health")
        async def health():
            return {"status": "placeholder", "message": "Z2 wave will implement full API"}

        return app
    except ImportError:
        print("FastAPI not installed - this is a placeholder for Z2 wave")
        return None


if __name__ == "__main__":
    app = create_app()
    if app:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8787)
    else:
        print("data-api placeholder: FastAPI not available")
