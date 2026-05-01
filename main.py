from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os
import numpy as np

from solver_ccx import process_socket_analysis
from biomechanics import MovementRequest, AnalyseBiomech

app = FastAPI(title="Unified Prosthetic Suite")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/analyze")
async def analyze_bio(request: MovementRequest):
    analyser = AnalyseBiomech(request)
    duration = analyser.get_duration()
    time_data = np.linspace(0, duration, 100)
    
    fx_data, fy_data, fz_data = analyser.calculate_3d_load_series(time_data)
    max_load = float(np.max(fz_data))
    
    return {
        "time_data": time_data.tolist(),
        "fz_data": fz_data.tolist(),
        "fy_data": fy_data.tolist(),
        "fx_data": fx_data.tolist(),
        "max_load": max_load
    }

@app.post("/api/calculate")
async def calculate_fem(
    file: UploadFile = File(...), 
    load_newtons: float = Form(...), 
    condition: str = Form("II"),
    mesh_size: float = Form(5.0),
    search_depth: float = Form(150.0),
    material: str = Form("petg_ortho")
):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
    try:
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
            "surface_faces": result.get("surface_faces", []),
            "stats": result.get("stats", {})
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

app.mount("/", StaticFiles(directory="static", html=True), name="static")