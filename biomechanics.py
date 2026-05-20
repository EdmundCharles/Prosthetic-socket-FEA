import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict

GAIT_PARAMS = {
    "walking": {
        "z1_amplitude": 1.12, "z1_phase": 0.135, "z1_width": 0.03, "z1_power": 2,
        "z3_amplitude": 1.12, "z3_phase": 0.465, "z3_width": 0.03, "z3_power": 2,
        "z2_base": 0.78, "z2_osc_amplitude": 0.22,
        "heel_strike_amplitude": 0.12, "heel_strike_phase": 0.01, "heel_strike_width": 0.008, "heel_strike_power": 2,
        "plateau_amplitude": 0.05, "plateau_phase": 0.05, "plateau_width": 0.02, "plateau_power": 4,
        "fy_braking_amplitude": -0.17, "fy_braking_phase": 0.10, "fy_braking_width": 0.03,
        "fy_propulsion_amplitude": 0.20, "fy_propulsion_phase": 0.48, "fy_propulsion_width": 0.04,
        "fx_first_amplitude": 0.05, "fx_first_phase": 0.12, "fx_first_width": 0.04,
        "fx_second_amplitude": -0.05, "fx_second_phase": 0.45, "fx_second_width": 0.04,
    },
    "jump": {
        "takeoff_amplitude": 2.5, "takeoff_phase": 0.35, "takeoff_width": 0.08,
        "landing_amplitude": 4.2, "landing_phase": 0.65, "landing_width": 0.06,
        "flight_min": 0.1,
    }
}

ALTERNATIVE_GAITS = {
    "fast": { "z1_amplitude": 1.18, "z1_phase": 0.12, "z3_amplitude": 1.15, "z3_phase": 0.44, "z2_base": 0.70, "fy_braking_amplitude": -0.20, "fy_propulsion_amplitude": 0.23 },
    "slow": { "z1_amplitude": 1.05, "z1_phase": 0.15, "z3_amplitude": 1.08, "z3_phase": 0.48, "z2_base": 0.85, "fy_braking_amplitude": -0.14, "fy_propulsion_amplitude": 0.16 },
    "elderly": { "z1_amplitude": 1.02, "z1_phase": 0.16, "z3_amplitude": 1.05, "z3_phase": 0.49, "z2_base": 0.82, "heel_strike_amplitude": 0.05, "fy_braking_amplitude": -0.12, "fy_propulsion_amplitude": 0.14, "fx_first_amplitude": 0.03, "fx_second_amplitude": -0.03 }
}

# ОБНОВЛЕНИЕ: Добавлены усталостные свойства для fatigue.py
MATERIALS_LIBRARY = {
    "carbon_fiber_high": {
        "name": "Карбон (высокопрочный)", "critical_load": 5000, 
        "type": "carbon", "uts": 800.0, "fatigue_intercept": 1200.0, "fatigue_slope": -0.08,
        "description": "Для активных пациентов, спортсменов, высокие нагрузки"
    },
    "carbon_fiber": {
        "name": "Карбон (стандарт)", "critical_load": 3000,
        "type": "carbon", "uts": 600.0, "fatigue_intercept": 850.0, "fatigue_slope": -0.1,
        "description": "Для обычной повседневной активности"
    },
    "carbon_fiber_light": {
        "name": "Карбон (облегченный)", "critical_load": 2000,
        "type": "carbon", "uts": 450.0, "fatigue_intercept": 600.0, "fatigue_slope": -0.11,
        "description": "Для легких пациентов, малая нагрузка"
    },
    "petg_reinforced": {
        "name": "PETG армированный", "critical_load": 1800,
        "type": "petg", "uts": 65.0, "fatigue_intercept": 90.0, "fatigue_slope": -0.09,
        "description": "Усиленный пластик для FGF печати"
    },
    "petg_standard": {
        "name": "PETG стандартный", "critical_load": 1200,
        "type": "petg", "uts": 50.0, "fatigue_intercept": 70.0, "fatigue_slope": -0.1,
        "description": "Базовый пластик для FGF печати"
    },
    "petg_light": {
        "name": "PETG облегченный", "critical_load": 800,
        "type": "petg", "uts": 40.0, "fatigue_intercept": 55.0, "fatigue_slope": -0.11,
        "description": "Легкий пластик, малая нагрузка"
    },
    "polypropylene": {
        "name": "Полипропилен", "critical_load": 600,
        "type": "petg", "uts": 30.0, "fatigue_intercept": 45.0, "fatigue_slope": -0.12,
        "description": "Дешевый материал, для пробных протезов"
    },
    "thermoplastic": {
        "name": "Термопластик", "critical_load": 400,
        "type": "petg", "uts": 25.0, "fatigue_intercept": 35.0, "fatigue_slope": -0.12,
        "description": "Бюджетный вариант, только для малых нагрузок"
    }
}

class SocketModel(BaseModel):
    material: str = Field(default="carbon_fiber", description="Материал гильзы")

class RequestBiomech(BaseModel):
    weight: float = Field(..., gt=0, lt=500, description="Вес человека в кг")
    height: float = Field(175, gt=100, lt=250, description="Рост в см")
    socket: SocketModel = Field(default_factory=SocketModel)
    movement_type: Literal["walking", "jump"] = Field(...)
    steps_per_day: int = Field(default=5000, ge=0)
    jump_height: Optional[float] = Field(None, gt=0, lt=3)

class ResponseBiomech(BaseModel):
    time_data: list[float]
    fx_data: list[float]
    fy_data: list[float]
    fz_data: list[float]
    max_load: float
    risk_percentage: float
    recommendations: list[str] = []

class AnalyseBiomech:
    def __init__(self, request: RequestBiomech, gait_profile: str = "normal"):
        self.request = request
        self.g = 9.81
        self.gait_profile = gait_profile
        
        material_key = request.socket.material
        if material_key in MATERIALS_LIBRARY:
            self.critical_load = MATERIALS_LIBRARY[material_key]["critical_load"]
        else:
            self.critical_load = 3000 
        
        if gait_profile in ALTERNATIVE_GAITS:
            self.params = GAIT_PARAMS.copy()
            for key, value in ALTERNATIVE_GAITS[gait_profile].items():
                if key in self.params["walking"]:
                    self.params["walking"][key] = value
        else:
            self.params = GAIT_PARAMS

    def get_duration(self) -> float:
        if self.request.movement_type == "jump":
            height = self.request.jump_height or 0.5
            return 2 * np.sqrt(2 * height / self.g) + 0.35
        height_m = self.request.height / 100
        return (height_m * 0.43) / 1.4

    def _gaussian_peak(self, t: np.ndarray, amplitude: float, center: float, width: float, power: int = 2) -> np.ndarray:
        return amplitude * np.exp(-((t - center) ** power) / (2 * width ** power))

    def calculate_load_series(self, time_array: np.ndarray) -> np.ndarray:
        mass = self.request.weight
        duration = self.get_duration()
        W = mass * self.g 
        
        if self.request.movement_type == "walking":
            p = self.params["walking"]
            t = time_array / duration
            base = W * (p["z2_base"] + p["z2_osc_amplitude"] * np.sin(np.pi * t))
            z1 = self._gaussian_peak(t, W * p["z1_amplitude"], p["z1_phase"], p["z1_width"], p.get("z1_power", 2))
            z3 = self._gaussian_peak(t, W * p["z3_amplitude"], p["z3_phase"], p["z3_width"], p.get("z3_power", 2))
            heel_strike = self._gaussian_peak(t, W * p["heel_strike_amplitude"], p["heel_strike_phase"], p["heel_strike_width"], p.get("heel_strike_power", 2))
            plateau = self._gaussian_peak(t, W * p["plateau_amplitude"], p["plateau_phase"], p["plateau_width"], p.get("plateau_power", 4))
            fz = base + z1 + z3 + heel_strike + plateau
            return np.where(time_array > duration, 0, fz)
        else: 
            p = self.params["jump"]
            t_takeoff = duration * p["takeoff_phase"]
            t_landing = duration * p["landing_phase"]
            takeoff_peak = (p["takeoff_amplitude"] * W) * np.exp(-((time_array - t_takeoff) ** 2) / (2 * (duration * p["takeoff_width"]) ** 2))
            landing_peak = (p["landing_amplitude"] * W) * np.exp(-((time_array - t_landing) ** 2) / (2 * (duration * p["landing_width"]) ** 2))
            load = takeoff_peak + landing_peak
            load = np.maximum(load, W * p.get("flight_min", 0.1))
            return np.where(time_array > duration, 0, load)

    def calculate_3d_load_series(self, time_array: np.ndarray):
        duration = self.get_duration()
        mass = self.request.weight
        g = self.g
        movement = self.request.movement_type
        t = time_array / duration
        weight = mass * g  
        
        fz = self.calculate_load_series(time_array)

        if movement == "jump":
            fy = np.zeros_like(time_array)
            fx = np.zeros_like(time_array)
        else:
            p = self.params["walking"] 
            fy = (p["fy_braking_amplitude"] * weight * self._gaussian_peak(t, 1.0, p["fy_braking_phase"], p["fy_braking_width"], 2)) + \
                 (p["fy_propulsion_amplitude"] * weight * self._gaussian_peak(t, 1.0, p["fy_propulsion_phase"], p["fy_propulsion_width"], 2))
            
            fx = (p["fx_first_amplitude"] * weight * self._gaussian_peak(t, 1.0, p["fx_first_phase"], p["fx_first_width"], 2)) + \
                 (p["fx_second_amplitude"] * weight * self._gaussian_peak(t, 1.0, p["fx_second_phase"], p["fx_second_width"], 2))
            
        return fx, fy, fz
    
    def get_critical_load(self) -> float:
        return self.critical_load

    def generate_recommendations(self, risk: float) -> list[str]:
        recs = []
        material = self.request.socket.material
        movement_type = self.request.movement_type
    
        if risk > 80 and risk < 100:
            recs.append("⚠️ ВНИМАНИЕ: Текущая нагрузка близка к критической. Избегайте резких прыжков.")
        elif risk >= 100:
            recs.append("🔴 ПРЕВЫШЕН ПРЕДЕЛ ПРОЧНОСТИ! Немедленно замените гильзу!")
        else:
            recs.append("🟢 Нагрузка в норме. Текущий режим активности безопасен для изделия.")

        if material == "thermoplastic" and risk > 70:
            recs.append("💡 СОВЕТ: Пластиковая гильза не справляется с вашей нагрузкой. Рекомендуется переход на карбон.")
        if material == "carbon_fiber" and risk < 30:
            recs.append("ℹ️ Запас прочности избыточен. Для снижения веса можно использовать более легкие материалы.")
        if movement_type == "jump" and risk > 60:
            recs.append("🏃‍♂️ Прыжки создают высокую ударную нагрузку. Рекомендуется ограничить их частоту.")
        return recs

    @staticmethod
    def get_available_profiles() -> list[str]:
        return ["normal"] + list(ALTERNATIVE_GAITS.keys())
