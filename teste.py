from fastapi import FastAPI

app = FastAPI()

@app.post("/simular-movimento")
def simular_movimento_manual():
    return {"status": "POST funcionando!"}
