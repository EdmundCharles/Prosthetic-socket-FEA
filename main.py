from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os
import numpy as np

# Твое новое промышленное МКЭ ядро
from solver_ccx import process_socket_analysis

# Логика коллеги
from biomechanics import MovementRequest, calculate_bio_load, get_recommendations

app = FastAPI(title="Unified Prosthetic Suite")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==========================================
# РОУТ 1: БИОМЕХАНИКА
# ==========================================
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

# ==========================================
# РОУТ 2: МКЭ И CALCULIX
# ==========================================
@app.post("/api/calculate")
async def calculate_fem(
    file: UploadFile = File(...), 
    load_newtons: float = Form(...), 
    condition: str = Form("II"),
    mesh_size: float = Form(5.0),
    search_depth: float = Form(150.0),
    material: str = Form("petg_ortho") # Принимаем материал
):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
    try:
        # Передаем всё в решатель
        result = process_socket_analysis(temp_path, load_newtons, condition, mesh_size, search_depth, material)
        return {
            "status": "success",
            "fem_nodes": result["nodes"],
            "displacements": result.get("displacements", []),
            "fem_values": result["fem_values"],
            "max_stress": result["max_stress"],
            "bottom_coords": result["bottom_nodes"],
            "top_coords": result["top_nodes"],
            "master_coords": result.get("master_coords", []), 
            "force_vector": result.get("force_vector", []),
            "surface_faces": result.get("surface_faces", []), # Добавили эту строку!
            "stats": result.get("stats", {})
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
# ==========================================
# СТАТИКА
# ==========================================
app.mount("/", StaticFiles(directory="static", html=True), name="static")