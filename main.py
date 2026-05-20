from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os
import numpy as np

from solver_ccx import process_socket_analysis
from biomechanics import RequestBiomech, AnalyseBiomech, ResponseBiomech, SocketModel, MATERIALS_LIBRARY
# ИМПОРТ ОБНОВЛЕННОЙ ФУНКЦИИ FDM
from fatigue import analyze_fdm_node_fatigue 

app = FastAPI(title="Unified Prosthetic Suite")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/analyze", response_model=ResponseBiomech)
async def analyze_bio(request: RequestBiomech):
    analyser = AnalyseBiomech(request)
    duration = analyser.get_duration()
    time_data = np.linspace(0, duration, 100)

    fx_data, fy_data, fz_data = analyser.calculate_3d_load_series(time_data)
    max_load = float(np.max(fz_data))
    material = request.socket.material
    risk_percentage = analyser.get_risk_percentage(max_load)
    recommendations = analyser.generate_recommendations(risk_percentage, material)

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
    bio_material: str = Form("carbon_fiber"),
    weight: float = Form(80.0),
    height: float = Form(175.0),
    kultya_girth: float = Form(30.0), 
    moveType: str = Form("walking"),
    stepsDay: int = Form(5000)
):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # 1. Решаем статику в МКЭ (теперь solver_ccx.py не делает усталость)
        result = process_socket_analysis(temp_path, load_newtons, condition, mesh_size, search_depth, material)
        
        # 2. Генерируем динамическую нагрузку шага
        req = RequestBiomech(weight=weight, height=height, kultya_girth=kultya_girth, 
                             movement_type=moveType, steps_per_day=stepsDay, socket=SocketModel(material=bio_material))
        analyser = AnalyseBiomech(req)
        time_data = np.linspace(0, analyser.get_duration(), 100)
        fx, fy, fz = analyser.calculate_3d_load_series(time_data)
        
        # 3. Линейная суперпозиция тензоров напряжений
        load_mag = np.sqrt(np.array(fx)**2 + np.array(fy)**2 + np.array(fz)**2)
        scaling_factors = load_mag / load_newtons
        
        base_tensor = np.array(result["critical_stress_voigt"]) 
        stress_history_voigt = np.outer(scaling_factors, base_tensor)
        
        # 4. Расчет усталости для FDM
        mat_props = MATERIALS_LIBRARY.get(bio_material, MATERIALS_LIBRARY["carbon_fiber"])
        # Берем оси по отдельности
        mat_ip = mat_props.get("ip", {"uts": 600.0, "fatigue_intercept": 850.0, "fatigue_slope": -0.1})
        mat_z  = mat_props.get("z", {"uts": 450.0, "fatigue_intercept": 600.0, "fatigue_slope": -0.12})
        
        fatigue_res = analyze_fdm_node_fatigue(stress_history_voigt, mat_ip, mat_z)
        damage_per_step = fatigue_res["total_damage"]
        
        if damage_per_step > 0 and damage_per_step < 1.0:
            life_days = 1.0 / (damage_per_step * stepsDay)
            life_years = round(life_days / 365.0, 2)
        elif damage_per_step >= 1.0:
            life_years = 0.0 # Разрушение сразу
        else:
            life_years = 50.0 # Бесконечный ресурс
            
        # Добавляем в результат прогнозные годы
        fatigue_res["estimated_life_years"] = life_years
            
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
            "fatigue_results": fatigue_res # Отдаем объект полностью на фронт
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
