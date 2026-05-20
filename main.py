from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os
import numpy as np

from solver_ccx1_pro import process_socket_analysis
from biomeh1_pro import RequestBiomech, AnalyseBiomech, ResponseBiomech, SocketModel, MATERIALS_LIBRARY
from fatigue import analyze_node_fatigue 

app = FastAPI(title="Unified Prosthetic Suite")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/analyze", response_model=ResponseBiomech)
async def analyze_bio(request: RequestBiomech):
    analyser = AnalyseBiomech(request)
    duration = analyser.get_duration()
    time_data = np.linspace(0, duration, 100)

    fx_data, fy_data, fz_data = analyser.calculate_3d_load_series(time_data)
    max_load = float(np.max(fz_data))
    critical_load = analyser.get_critical_load()
    risk_percentage = min((max_load / critical_load) * 100.0, 100.0)
    recommendations = analyser.generate_recommendations(risk_percentage)

    return ResponseBiomech(
        time_data=time_data.tolist(), fx_data=fx_data.tolist(),
        fy_data=fy_data.tolist(), fz_data=fz_data.tolist(),
        max_load=max_load, risk_percentage=risk_percentage, recommendations=recommendations
    )

@app.post("/api/calculate")
async def calculate_fem(
    file: UploadFile = File(...), 
    load_newtons: float = Form(...), 
    condition: str = Form("II"),
    mesh_size: float = Form(5.0),
    search_depth: float = Form(150.0),
    material: str = Form("petg_ortho"),
    # === НОВЫЕ ПАРАМЕТРЫ ДЛЯ УСТАЛОСТИ ===
    bio_material: str = Form("carbon_fiber"),
    weight: float = Form(80.0),
    moveType: str = Form("walking"),
    stepsDay: int = Form(5000)
):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # 1. Решаем статику в МКЭ
        result = process_socket_analysis(temp_path, load_newtons, condition, mesh_size, search_depth, material)
        
        # 2. Генерируем динамическую нагрузку шага
        req = RequestBiomech(weight=weight, movement_type=moveType, steps_per_day=stepsDay, socket=SocketModel(material=bio_material))
        analyser = AnalyseBiomech(req)
        time_data = np.linspace(0, analyser.get_duration(), 100)
        fx, fy, fz = analyser.calculate_3d_load_series(time_data)
        
        # 3. Линейная суперпозиция тензоров напряжений
        load_mag = np.sqrt(np.array(fx)**2 + np.array(fy)**2 + np.array(fz)**2)
        scaling_factors = load_mag / load_newtons
        
        base_tensor = np.array(result["critical_stress_voigt"]) 
        stress_history_voigt = np.outer(scaling_factors, base_tensor)
        
        # 4. Расчет усталости
        mat_props = MATERIALS_LIBRARY.get(bio_material, MATERIALS_LIBRARY["carbon_fiber"])
        material_params = {
            "type": mat_props.get("type", "carbon"),
            "uts": mat_props.get("uts", 600.0),
            "fatigue_intercept": mat_props.get("fatigue_intercept", 850.0),
            "fatigue_slope": mat_props.get("fatigue_slope", -0.1)
        }
        
        damage_per_step = analyze_node_fatigue(stress_history_voigt, material_params)
        
        if damage_per_step > 0:
            life_days = 1.0 / (damage_per_step * stepsDay)
            life_years = round(life_days / 365.0, 2)
        else:
            life_years = 50.0 
            
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
            "stats": result.get("stats", {}),
            "fatigue_results": { "estimated_life_years": life_years } # <--- Возвращаем на фронт
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
