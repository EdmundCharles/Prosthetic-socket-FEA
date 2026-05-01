import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional

class SocketModel(BaseModel):
    material: str = Field(default="carbon_fiber")
    critical_load: float = Field(default=3000, gt=0)

class MovementRequest(BaseModel):
    weight: float = Field(..., gt=0)
    height: float = Field(175, gt=100, lt=250)
    thigh_girth: float = Field(50, gt=20, lt=100)
    socket: SocketModel = Field(default_factory=SocketModel)
    movement_type: Literal["walking", "running", "jump"] = Field(...)
    steps_per_day: int = Field(default=5000, ge=0)
    speed: Optional[float] = Field(None, gt=0, lt=15)
    jump_height: Optional[float] = Field(None, gt=0, lt=3)

class AnalyseBiomech:
    def __init__(self, request: MovementRequest):
        self.request = request
        self.g = 9.81

    def get_duration(self) -> float:
        if self.request.movement_type == "jump":
            height = self.request.jump_height or 0.5
            return 2 * np.sqrt(2 * height / self.g)
        
        height_m = self.request.height / 100
        stride_length = height_m * 0.43
        speed = self.request.speed or (1.4 if self.request.movement_type == "walking" else 3.0)
        return stride_length / speed

    def calculate_load_series(self, time_array: np.ndarray) -> np.ndarray:
        mass = self.request.weight
        duration = self.get_duration()
        if self.request.movement_type == "walking":
            return mass * self.g * (1.2 + 1.0 * np.abs(np.sin(2 * np.pi * time_array / duration)))
        elif self.request.movement_type == "running":
            t_mod = (time_array % duration) / duration
            load = mass * self.g * (2.5 + 3.5 * np.exp(-8 * t_mod) * np.sin(np.pi * t_mod))
            return np.maximum(load, mass * self.g * 1.2)
        else:
            impact_time = duration / 2
            load = mass * self.g * (1 + 3 * np.exp(-50 * (time_array - impact_time)**2))
            return np.where(time_array > duration, 0, load)

    def calculate_3d_load_series(self, time_array: np.ndarray):
        duration = self.get_duration()
        mass = self.request.weight
        fz = self.calculate_load_series(time_array) 
        fy = 0.2 * mass * self.g * np.sin(2 * np.pi * time_array / duration)
        fx = 0.05 * mass * self.g * np.cos(np.pi * time_array / duration)
        return fx, fy, fz