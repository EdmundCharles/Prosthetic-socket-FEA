from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os

from solver import process_and_simulate  # Твое МКЭ ядро
from biomechanics import MovementRequest, calculate_bio_load, get_recommendations # Коллега
import numpy as np

app = FastAPI(title="Unified Prosthetic Suite")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/analyze")
async def analyze_bio(request: MovementRequest):
    time_data, load_data, duration = calculate_bio_load(request)
    max_load = float(np.max(load_data))
    risk = (max_load / request.socket.critical_load) * 100
    
    # Упрощенный Баскин
    cycles = 0.5 * (max_load / request.socket.fatigue_intercept) ** (1 / request.socket.fatigue_slope)
    service_life = round(cycles / (request.steps_per_day * 365), 1)
    
    return {
        "time_data": time_data.tolist(),
        "load_data": load_data.tolist(),
        "max_load": max_load,
        "service_life": service_life,
        "recommendations": get_recommendations(max_load, risk, service_life, request.movement_type, request.socket.material)
    }

@app.post("/api/calculate")
async def calculate_fem(file: UploadFile = File(...), load_newtons: float = Form(...), offset_x: float = Form(0.0), offset_y: float = Form(0.0)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    try:
        return process_and_simulate(temp_path, load_newtons, offset_x, offset_y)
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

app.mount("/", StaticFiles(directory="static", html=True), name="static")