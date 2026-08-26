from fastapi import FastAPI

from app.brand.router import router as brand_router

app = FastAPI(
    title="AI Landing Page Generator API",
    version="0.1.0",
)

app.include_router(brand_router, prefix="/api")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
