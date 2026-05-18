from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os

from solver_ccx import process_socket_analysis # МКЭ ядро
from biomechanics import RequestBiomech, AnalyseBiomech, ResponseBiomech # Биомеханика
import numpy as np

app = FastAPI(title="Unified Prosthetic Suite")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/analyze", response_model=ResponseBiomech)
async def analyze_bio(request: RequestBiomech):
    """
    Анализ нагрузки на гильзу протеза при движении.
    
    Принимает параметры движения и возвращает:
    - Временной ряд нагрузки
    - Максимальную нагрузку
    - Риск повреждения в %
    - Срок службы
    - Рекомендации по эксплуатации и материалу
    """
    #Экземпляр анализатора
    analyser = AnalyseBiomech(request)
    
    # Рассчитываем циклическую нагрузку
    duration = analyser.get_duration()
    time_data = np.linspace(0, duration, 100)

    # Получаем 3D векторы
    fx_data, fy_data, fz_data = analyser.calculate_3d_load_series(time_data)

    # Находим максимальную нагрузку, риск, срок службы и рекомендации
    max_load = float(np.max(fz_data))
    critical_load = request.socket.critical_load
    risk_percentage = min((max_load / critical_load) * 100, 100)
    service_life = analyser.calculate_service_life(max_load)
    recommendations = analyser.generate_recommendations(max_load, risk_percentage, service_life)
    
    return ResponseBiomech(
        time_data=time_data.tolist(),
        critical_load=critical_load,
        fx_data=fx_data.tolist(),
        fy_data=fy_data.tolist(),
        fz_data=fz_data.tolist(),
        max_load=max_load,
        risk_percentage=risk_percentage,
        service_life=service_life,
        recommendations=recommendations
    )

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