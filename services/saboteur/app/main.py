from fastapi import FastAPI
from pydantic import BaseModel
from services.saboteur.app.injector import chaos_injector
from shared.logger import setup_logger

logger = setup_logger("service-3-saboteur")
app = FastAPI(title="Service 3 — Saboteur / Chaos Injector", version="1.0.0")

class ChaosConfigUpdate(BaseModel):
    enabled: bool
    seed: int
    prompt_rate: float
    packet_drop_rate: float
    tool_503_rate: float

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "saboteur",
        "enabled": chaos_injector.enabled,
        "seed": chaos_injector.seed
    }

@app.post("/chaos/reset-seed")
def reset_seed(seed: int):
    chaos_injector.reset_seed(seed)
    logger.info(f"Saboteur seed reset to: {seed}")
    return {"status": "ok", "seed": seed}

@app.post("/chaos/config")
def update_config(config: ChaosConfigUpdate):
    chaos_injector.set_enabled(config.enabled)
    chaos_injector.reset_seed(config.seed)
    chaos_injector.prompt_rate = config.prompt_rate
    chaos_injector.packet_drop_rate = config.packet_drop_rate
    chaos_injector.tool_503_rate = config.tool_503_rate
    logger.info(f"Saboteur configuration updated: {config}")
    return {"status": "ok", "config": config.model_dump()}
