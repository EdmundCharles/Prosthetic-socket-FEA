import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional

class SocketModel(BaseModel):
    material: str = "carbon_fiber"
    critical_load: float = 3000
    fatigue_intercept: float = 5000
    fatigue_slope: float = -0.1

class MovementRequest(BaseModel):
    weight: float
    height: float = 175
    thigh_girth: float
    socket: SocketModel = SocketModel()
    movement_type: Literal["walking", "running", "jump"]
    steps_per_day: int = 5000
    speed: Optional[float] = None
    jump_height: Optional[float] = None

def calculate_bio_load(request: MovementRequest):
    g = 9.81
    mass = request.weight
    height_m = request.height / 100
    stride_length = height_m * 0.43
    
    if request.movement_type == "jump":
        duration = 2 * np.sqrt(2 * (request.jump_height or 0.5) / g)
    else:
        speed = request.speed or (1.4 if request.movement_type == "walking" else 3.0)
        duration = stride_length / speed

    time_data = np.linspace(0, duration, 100)
    
    if request.movement_type == "walking":
        load = mass * g * (1.2 + 1.0 * np.abs(np.sin(2 * np.pi * time_data / duration)))
    elif request.movement_type == "running":
        t_mod = (time_data % duration) / duration
        load = mass * g * (2.5 + 3.5 * np.exp(-8 * t_mod) * np.sin(np.pi * t_mod))
        load = np.maximum(load, mass * g * 1.2)
    else:
        impact_time = duration / 2
        load = mass * g * (1 + 3 * np.exp(-50 * (time_data - impact_time)**2))
        load = np.where(time_data > duration, 0, load)
        
    return time_data, load, duration

def get_recommendations(max_load, risk, service_life, movement_type, material):
    recs = []
    if risk > 80: recs.append("⚠️ Нагрузка близка к критической!")
    if service_life < 2: recs.append("🔴 Срок службы критически мал. Проверьте адгезию слоев FGF.")
    if material == "thermoplastic" and risk > 70: recs.append("💡 Перейдите на карбон или увеличьте плотность заполнения.")
    return recs