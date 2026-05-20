import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict

GAIT_PARAMS = {
    "walking": {
        # ===== ПАРАМЕТРЫ Fz (вертикальная сила) =====
        # Пик Z1 (первый пик, ускорение подъема)
        "z1_amplitude": 1.12,      # 112% веса тела
        "z1_phase": 0.135,         # 13.5% цикла шага
        "z1_width": 0.03,          # Ширина пика
        "z1_power": 2,             # Степень (2 - гауссиана, 4 - более плоский)
        
        # Пик Z3 (второй пик, ускорение падения)
        "z3_amplitude": 1.12,      # 112% веса тела
        "z3_phase": 0.465,         # 46.5% цикла шага
        "z3_width": 0.03,          # Ширина пика
        "z3_power": 2,             # Степень
        
        # Минимум Z2 (инерционный минимум)
        "z2_base": 0.78,           # Базовый минимум 78% веса
        "z2_osc_amplitude": 0.22,  # Амплитуда синусоидальной составляющей
        
        # Обратный зубец (удар пяткой в начале цикла)
        "heel_strike_amplitude": 0.12,   # 12% веса
        "heel_strike_phase": 0.01,       # 1% цикла
        "heel_strike_width": 0.008,      # Ширина
        "heel_strike_power": 2,
        
        # Плато (смена направления ускорения, 2-8% цикла)
        "plateau_amplitude": 0.05,       # 5% веса
        "plateau_phase": 0.05,           # 5% цикла
        "plateau_width": 0.02,           # Ширина
        "plateau_power": 4,              # Более плоское плато
        
        # ===== ПАРАМЕТРЫ Fy (продольная сила) =====
        "fy_braking_amplitude": -0.17,   # Пик торможения (% веса) - отрицательный
        "fy_braking_phase": 0.10,        # Фаза пика торможения (10% цикла)
        "fy_braking_width": 0.03,        # Ширина пика торможения
        
        "fy_propulsion_amplitude": 0.20, # Пик ускорения (% веса) - положительный
        "fy_propulsion_phase": 0.52,     # Фаза пика ускорения (52% цикла)
        "fy_propulsion_width": 0.04,     # Ширина пика ускорения
        
        # ===== ПАРАМЕТРЫ Fx (боковая сила) =====
        "fx_first_amplitude": -0.04,      # Первый пик 
        "fx_first_phase": 0.16,          # Фаза первого пика (16% цикла)
        "fx_first_width": 0.04,          # Ширина первого пика
        
        "fx_second_amplitude": -0.03,    # Второй пик 
        "fx_second_phase": 0.42,         # Фаза второго пика (42% цикла)
        "fx_second_width": 0.04,         # Ширина второго пика

        "fx_min_amplitude": -0.03,        # Минимум между пиками
        "fx_min_phase": 0.30,             # Фаза минимума (30% цикла)
        "fx_min_width": 0.08,             # Ширина минимума
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

# ОБНОВЛЕННАЯ БАЗА МАТЕРИАЛОВ ДЛЯ DUAL DAMAGE MODEL
MATERIALS_LIBRARY = {
    "carbon_fiber_high": {
        "name": "Карбон (высокопрочный)", "type": "carbon",
        "ip": {"uts": 800.0, "fatigue_intercept": 1200.0, "fatigue_slope": -0.08},
        "z": {"uts": 650.0, "fatigue_intercept": 900.0, "fatigue_slope": -0.10},
        "description": "Для активных пациентов, высокие нагрузки"
    },
    "carbon_fiber": {
        "name": "Карбон (стандарт)", "type": "carbon",
        "ip": {"uts": 600.0, "fatigue_intercept": 850.0, "fatigue_slope": -0.1},
        "z": {"uts": 450.0, "fatigue_intercept": 600.0, "fatigue_slope": -0.12},
        "description": "Для обычной повседневной активности"
    },
    "carbon_fiber_light": {
        "name": "Карбон (облегченный)", "type": "carbon",
        "ip": {"uts": 450.0, "fatigue_intercept": 600.0, "fatigue_slope": -0.11},
        "z": {"uts": 300.0, "fatigue_intercept": 400.0, "fatigue_slope": -0.13},
        "description": "Для легких пациентов, малая нагрузка"
    },
    "petg_reinforced": {
        "name": "PETG армированный", "type": "petg",
        "ip": {"uts": 65.0, "fatigue_intercept": 90.0, "fatigue_slope": -0.09},
        "z": {"uts": 45.0, "fatigue_intercept": 60.0, "fatigue_slope": -0.12},
        "description": "Усиленный пластик для FGF печати"
    },
    "petg_standard": {
        "name": "PETG стандартный", "type": "petg",
        "ip": {"uts": 50.0, "fatigue_intercept": 70.0, "fatigue_slope": -0.1},
        "z": {"uts": 30.0, "fatigue_intercept": 45.0, "fatigue_slope": -0.15},
        "description": "Базовый пластик для FGF печати"
    },
    "petg_light": {
        "name": "PETG облегченный", "type": "petg",
        "ip": {"uts": 40.0, "fatigue_intercept": 55.0, "fatigue_slope": -0.11},
        "z": {"uts": 25.0, "fatigue_intercept": 35.0, "fatigue_slope": -0.16},
        "description": "Легкий пластик, малая нагрузка"
    },
    "polypropylene": {
        "name": "Полипропилен", "type": "petg",
        "ip": {"uts": 30.0, "fatigue_intercept": 45.0, "fatigue_slope": -0.12},
        "z": {"uts": 20.0, "fatigue_intercept": 28.0, "fatigue_slope": -0.16},
        "description": "Дешевый материал, для пробных протезов"
    },
    "thermoplastic": {
        "name": "Термопластик", "type": "petg",
        "ip": {"uts": 25.0, "fatigue_intercept": 35.0, "fatigue_slope": -0.12},
        "z": {"uts": 15.0, "fatigue_intercept": 20.0, "fatigue_slope": -0.18},
        "description": "Бюджетный вариант, только для малых нагрузок"
    }
}

class SocketModel(BaseModel):
    material: str = Field(default="carbon_fiber", description="Материал гильзы")

class RequestBiomech(BaseModel):
    weight: float = Field(..., gt=0, lt=500, description="Вес человека в кг")
    height: float = Field(..., gt=100, lt=250, description="Рост в см")
    kultya_girth: float = Field(..., gt=0, lt=100, description="Обхват культи в см")
    steps_per_day: int = Field(default=5000, ge=0)
    movement_type: Literal["walking", "jump"] = Field(...)
    jump_height: Optional[float] = Field(None, gt=0, lt=3)
    socket: SocketModel = Field(default_factory=SocketModel)

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
        
        # Забираем параметры слабого звена (ось Z) для консервативной статической оценки
        material_key = request.socket.material
        if material_key in MATERIALS_LIBRARY:
            mat_info = MATERIALS_LIBRARY[material_key]
            self.uts = mat_info["z"]["uts"]
            self.material_type = mat_info["type"]
        else:
            self.uts = 450.0 
            self.material_type = "carbon"
        
        if gait_profile in ALTERNATIVE_GAITS:
            self.params = GAIT_PARAMS.copy()
            for key, value in ALTERNATIVE_GAITS[gait_profile].items():
                if key in self.params["walking"]:
                    self.params["walking"][key] = value
        else:
            self.params = GAIT_PARAMS

        self.kultya_girth_m = request.kultya_girth / 100.0
        self.uts_pa = self.uts * 10**6 

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
            
            # ==================================================
            # 1. ПРОДОЛЬНАЯ СИЛА (Fy) - Торможение и ускорение
            # ==================================================
            # Пик торможения (отрицательный, в начале цикла)
            braking_peak = p["fy_braking_amplitude"] * weight * self._gaussian_peak(
                t, 1.0, p["fy_braking_phase"], p["fy_braking_width"], 2
            )
            
            # Пик ускорения (положительный, во второй половине цикла)
            propulsion_peak = p["fy_propulsion_amplitude"] * weight * self._gaussian_peak(
                t, 1.0, p["fy_propulsion_phase"], p["fy_propulsion_width"], 2
            )
            
            fy = braking_peak + propulsion_peak
            
            # ==================================================
            # 2. ПОПЕРЕЧНАЯ СИЛА (Fx) - Боковая стабилизация
            # ==================================================
            # Первый пик (положительный, на наблюдателя)
            first_peak = p["fx_first_amplitude"] * weight * self._gaussian_peak(
                t, 1.0, p["fx_first_phase"], p["fx_first_width"], 2
            )
            
            # Второй пик (отрицательный, от наблюдателя)
            second_peak = p["fx_second_amplitude"] * weight * self._gaussian_peak(
                t, 1.0, p["fx_second_phase"], p["fx_second_width"], 2
            )

            min_peak = p["fx_min_amplitude"] * weight * self._gaussian_peak(
                t, 1.0, p["fx_min_phase"], p["fx_min_width"], 4  # power=4 для более плоского дна
            )

            fx = first_peak + second_peak + min_peak
    
            
        return fx, fy, fz
    
    def get_tensile_strength(self) -> float:
        """Возвращает предел прочности"""
        return self.tensile_strength
    
    def get_risk_percentage(self, max_load: float) -> float:
        """Вычисляем риск повреждения протеза"""
        R = self.kultya_girth_m / (2*np.pi)
        S = np.pi * R**2
        sigma = max_load/S
        risk_percentage = min((sigma / self.uts_pa) * 100.0, 100.0)
        return risk_percentage

    def generate_recommendations(self, risk: float, material: str) -> list[str]:
        recs = []
        movement_type = self.request.movement_type
    
        if risk > 80 and risk < 100:
            recs.append("Внимание: Расчетная нагрузка близка к критическим значениям. Рекомендуется избегать ударных воздействий.")
        elif risk >= 100:
            recs.append("Критический уровень риска: Превышен предел прочности конструкции. Эксплуатация изделия недопустима.")
        else:
            recs.append("Нагрузка в пределах нормы. Текущий режим эксплуатации безопасен для выбранной конструкции.")

        if material == "thermoplastic" and risk > 70:
            recs.append("Материал (термопласт) имеет недостаточный запас прочности для данного профиля активности. Рекомендуется рассмотреть углепластик.")
        if material in ["carbon_fiber", "carbon_fiber_high", "carbon_fiber_light"] and risk < 30:
            recs.append("Запас прочности избыточен. Допускается оптимизация толщины стенки или использование менее жестких материалов для снижения веса.")
        if movement_type == "jump" and risk > 60:
            recs.append("Регулярные ударные нагрузки (прыжки) могут привести к ускоренному усталостному износу. Рекомендуется ограничить частоту.")
        return recs

    @staticmethod
    def get_available_profiles() -> list[str]:
        return ["normal"] + list(ALTERNATIVE_GAITS.keys())
