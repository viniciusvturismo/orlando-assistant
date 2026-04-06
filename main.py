import uvicorn
from src.api.main import app
from src.channel.whatsapp_handler import router as whatsapp_router

# Registra o router do canal no app principal
app.include_router(whatsapp_router)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
