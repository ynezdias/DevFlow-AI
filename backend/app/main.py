from fastapi import FastAPI

app = FastAPI(
    title="DevFlow AI",
    description="AI-powered pull request review platform",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "service": "DevFlow AI",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }