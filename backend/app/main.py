from fastapi import FastAPI

app = FastAPI(title="GreenSync Backend")


@app.get("/")
def health_check():
    """Endpoint simples pra confirmar que o backend está de pé."""
    return {"status": "ok"}