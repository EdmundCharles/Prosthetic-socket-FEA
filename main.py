from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os

from solver import process_and_simulate  # МКЭ ядро
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
    load_data = analyser.calculate_load_series(time_data)

    # Находим максимальную нагрузку, риск, срок службы и рекомендации
    max_load = float(np.max(load_data))
    critical_load = request.socket.critical_load
    risk_percentage = min((max_load / critical_load) * 100, 100)
    service_life = analyser.calculate_service_life(max_load)
    recommendations = analyser.generate_recommendations(max_load, risk_percentage, service_life)
    
    return ResponseBiomech(
        time_data=time_data.tolist(),
        load_data=load_data.tolist(),
        critical_load=critical_load,
        max_load=max_load,
        risk_percentage=risk_percentage,
        service_life=service_life,
        recommendations=recommendations
    )

@app.post("/api/calculate")
async def calculate_fem(file: UploadFile = File(...), load_newtons: float = Form(...), offset_x: float = Form(0.0), offset_y: float = Form(0.0)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    try:
        return process_and_simulate(temp_path, load_newtons, offset_x, offset_y)
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

app.mount("/", StaticFiles(directory="static", html=True), name="static")