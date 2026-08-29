from fastapi import FastAPI

app = FastAPI(title="URL Shortener Service")


@app.get("/health")
def health_check():
    return {"status": "ok"}