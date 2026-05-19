import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict

# ========== ПАРАМЕТРЫ ГРАФИКОВ ДЛЯ НАСТРОЙКИ ==========
# Можно быстро менять эти значения для калибровки графика

GAIT_PARAMS = {
    "walking": {
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
    },
    
    "jump": {
        # Отталкивание
        "takeoff_amplitude": 2.5,    # 250% веса
        "takeoff_phase": 0.35,       # 35% цикла
        "takeoff_width": 0.08,       # Ширина
        
        # Приземление
        "landing_amplitude": 4.2,    # 420% веса
        "landing_phase": 0.65,       # 65% цикла
        "landing_width": 0.06,       # Ширина
        
        # Полетная фаза (минимальная нагрузка)
        "flight_min": 0.1,           # 10% веса
    }
}

# Альтернативные профили для разных типов пациентов
ALTERNATIVE_GAITS = {
    "fast": {
        "z1_amplitude": 1.18,
        "z1_phase": 0.12,
        "z3_amplitude": 1.15,
        "z3_phase": 0.44,
        "z2_base": 0.70,
    },
    "slow": {
        "z1_amplitude": 1.05,
        "z1_phase": 0.15,
        "z3_amplitude": 1.08,
        "z3_phase": 0.48,
        "z2_base": 0.85,
    },
    "elderly": {
        "z1_amplitude": 1.02,
        "z1_phase": 0.16,
        "z3_amplitude": 1.05,
        "z3_phase": 0.49,
        "z2_base": 0.82,
        "heel_strike_amplitude": 0.05,
    }
}

MATERIALS_LIBRARY = {
    "carbon_fiber_high": {
        "name": "Карбон (высокопрочный)",
        "critical_load": 5000,  # Ньютонов
        "description": "Для активных пациентов, спортсменов, высокие нагрузки"
    },
    "carbon_fiber": {
        "name": "Карбон (стандарт)",
        "critical_load": 3000,
        "description": "Для обычной повседневной активности"
    },
    "carbon_fiber_light": {
        "name": "Карбон (облегченный)",
        "critical_load": 2000,
        "description": "Для легких пациентов, малая нагрузка"
    },
    "petg_reinforced": {
        "name": "PETG армированный",
        "critical_load": 1800,
        "description": "Усиленный пластик для FGF печати"
    },
    "petg_standard": {
        "name": "PETG стандартный",
        "critical_load": 1200,
        "description": "Базовый пластик для FGF печати"
    },
    "petg_light": {
        "name": "PETG облегченный",
        "critical_load": 800,
        "description": "Легкий пластик, малая нагрузка"
    },
    "polypropylene": {
        "name": "Полипропилен",
        "critical_load": 600,
        "description": "Дешевый материал, для пробных протезов"
    },
    "thermoplastic": {
        "name": "Термопластик",
        "critical_load": 400,
        "description": "Бюджетный вариант, только для малых нагрузок"
    }
}

# ===== PYDANTIC МОДЕЛИ =====

class SocketModel(BaseModel):
    '''Параметры гильзы протеза'''
    material: str = Field(default="carbon_fiber", description="Материал гильзы")

class RequestBiomech(BaseModel):
    '''Данные с фронтенда при запросе'''
    weight: float = Field(..., gt=0, lt=500, description="Вес человека в кг")
    height: float = Field(175, gt=100, lt=250, description="Рост в см")
    socket: SocketModel = Field(default_factory=SocketModel)
    movement_type: Literal["walking", "jump"] = Field(...)
    steps_per_day: int = Field(default=5000, ge=0)
    jump_height: Optional[float] = Field(None, gt=0, lt=3)

class ResponseBiomech(BaseModel):
    """Ответ API с результатами анализа"""
    time_data: list[float]
    fx_data: list[float]
    fy_data: list[float]
    fz_data: list[float]
    max_load: float
    risk_percentage: float
    recommendations: list[str] = []

# ===== РАСЧЕТНЫЙ КЛАСС =====

class AnalyseBiomech:
    """Класс для биомеханического анализа нагрузки"""
    
    def __init__(self, request: RequestBiomech, gait_profile: str = "normal"):
        self.request = request
        self.g = 9.81
        self.gait_profile = gait_profile
        
        # Получаем critical_load из библиотеки материалов
        material_key = request.socket.material
        if material_key in MATERIALS_LIBRARY:
            self.critical_load = MATERIALS_LIBRARY[material_key]["critical_load"]
        else:
            self.critical_load = 3000  # Значение по умолчанию
        
        # Выбираем параметры графика
        if gait_profile in ALTERNATIVE_GAITS:
            self.params = GAIT_PARAMS.copy()
            for key, value in ALTERNATIVE_GAITS[gait_profile].items():
                if key in self.params["walking"]:
                    self.params["walking"][key] = value
        else:
            self.params = GAIT_PARAMS

    def get_duration(self) -> float:
        """Рассчитывает длительность цикла движения"""
        if self.request.movement_type == "jump":
            height = self.request.jump_height or 0.5
            flight_time = 2 * np.sqrt(2 * height / self.g)
            prep_time = 0.35
            return flight_time + prep_time
        
        # Ходьба
        height_m = self.request.height / 100
        stride_length = height_m * 0.43
        speed = 1.4
        return stride_length / speed

    def _gaussian_peak(self, t: np.ndarray, amplitude: float, center: float, 
                       width: float, power: int = 2) -> np.ndarray:
        """
        Генерирует пик заданной формы
        
        Parameters:
        - t: нормированное время (0..1)
        - amplitude: амплитуда
        - center: центр пика (0..1)
        - width: ширина пика
        - power: степень (2 - обычная гауссиана, 4 - более плоская вершина)
        """
        return amplitude * np.exp(-((t - center) ** power) / (2 * width ** power))

    def calculate_load_series(self, time_array: np.ndarray) -> np.ndarray:
        """Генерирует кривую вертикальной нагрузки Fz"""
        mass = self.request.weight
        duration = self.get_duration()
        W = mass * self.g  # Вес тела в Ньютонах
        
        if self.request.movement_type == "walking":
            p = self.params["walking"]
            
            # Нормированное время от 0 до 1
            t = time_array / duration
            
            # 1. Базовый уровень (синусоида между p["z2_base"]*W и W)
            base = W * (p["z2_base"] + p["z2_osc_amplitude"] * np.sin(np.pi * t))
            
            # 2. Пик Z1 (первый максимум)
            z1 = self._gaussian_peak(
                t, W * p["z1_amplitude"], p["z1_phase"], 
                p["z1_width"], p.get("z1_power", 2)
            )
            
            # 3. Пик Z3 (второй максимум)
            z3 = self._gaussian_peak(
                t, W * p["z3_amplitude"], p["z3_phase"], 
                p["z3_width"], p.get("z3_power", 2)
            )
            
            # 4. Обратный зубец (удар пяткой)
            heel_strike = self._gaussian_peak(
                t, W * p["heel_strike_amplitude"], p["heel_strike_phase"],
                p["heel_strike_width"], p.get("heel_strike_power", 2)
            )
            
            # 5. Плато (смена направления ускорения)
            plateau = self._gaussian_peak(
                t, W * p["plateau_amplitude"], p["plateau_phase"],
                p["plateau_width"], p.get("plateau_power", 4)
            )
            
            # Суммируем все компоненты
            fz = base + z1 + z3 + heel_strike + plateau
            
            # Обнуляем после завершения цикла
            return np.where(time_array > duration, 0, fz)
            
        else:  # jump
            p = self.params["jump"]
            t_takeoff = duration * p["takeoff_phase"]
            t_landing = duration * p["landing_phase"]
            width_takeoff = duration * p["takeoff_width"]
            width_landing = duration * p["landing_width"]
            
            amplitude_takeoff = p["takeoff_amplitude"] * W
            amplitude_landing = p["landing_amplitude"] * W
            
            takeoff_peak = amplitude_takeoff * np.exp(-((time_array - t_takeoff) ** 2) / (2 * width_takeoff ** 2))
            landing_peak = amplitude_landing * np.exp(-((time_array - t_landing) ** 2) / (2 * width_landing ** 2))
            
            load = takeoff_peak + landing_peak
            load = np.maximum(load, W * p.get("flight_min", 0.1))
            
            return np.where(time_array > duration, 0, load)

    def calculate_3d_load_series(self, time_array: np.ndarray):
        duration = self.get_duration()
        mass = self.request.weight
        g = self.g
        movement = self.request.movement_type
        
        # Нормированное время (0..1)
        t = time_array / duration
        # Вес тела в ньютонах
        weight = mass * g  
        
        # Fz - Вертикальная сила
        fz = self.calculate_load_series(time_array)

        if movement == "jump":
            # Для прыжка горизонтальные силы минимальны
            fy = np.zeros_like(time_array)
            fx = np.zeros_like(time_array)
        else:  # walking
            # 1. ПРОДОЛЬНАЯ СИЛА (Fy)
            # Используем синусоиду для имитации перехода от торможения к ускорению
            # Амплитуда ~0.2 * Вес тела (20% от веса)
            fy = 0.2 * weight * np.sin(2 * np.pi * t)
            
            # 2. ПОПЕРЕЧНАЯ СИЛА (Fx)
            # Аппроксимация кривой с двумя максимумами
            # Первый пик (X1, отведение) на 12% цикла
            # Второй пик (X2, приведение) на 45% цикла
            x1_amp = -0.05 * weight * np.exp(-((t - 0.12) ** 2) / (2 * 0.04 ** 2))
            x2_amp = 0.05 * weight * np.exp(-((t - 0.45) ** 2) / (2 * 0.04 ** 2))
            fx = x1_amp + x2_amp
            
        return fx, fy, fz
    
    def get_critical_load(self) -> float:
        """Возвращает критическую нагрузку для выбранного материала"""
        return self.critical_load

    def generate_recommendations(self, risk: float) -> list[str]:
        """Формирует список советов на основе риска повреждения"""
        recs = []
        material = self.request.socket.material
        movement_type = self.request.movement_type
    
        # Анализ статического риска
        if risk > 80 and risk < 100:
            recs.append("⚠️ ВНИМАНИЕ: Текущая нагрузка близка к критической. Избегайте резких прыжков.")
        elif risk >= 100:
            recs.append("🔴 ПРЕВЫШЕН ПРЕДЕЛ ПРОЧНОСТИ! Немедленно замените гильзу!")
        else:
            recs.append("🟢 Нагрузка в норме. Текущий режим активности безопасен для изделия.")

        # Советы по материалу
        if material == "thermoplastic" and risk > 70:
            recs.append("💡 СОВЕТ: Пластиковая гильза не справляется с вашей нагрузкой. Рекомендуется переход на карбон.")
        
        if material == "carbon_fiber" and risk < 30:
            recs.append("ℹ️ Запас прочности избыточен. Для снижения веса можно использовать более легкие материалы.")

        # Советы по типу движения
        if movement_type == "jump" and risk > 60:
            recs.append("🏃‍♂️ Прыжки создают высокую ударную нагрузку. Рекомендуется ограничить их частоту.")

        return recs

    @staticmethod
    def get_available_profiles() -> list[str]:
        """Возвращает список доступных профилей походки"""
        return ["normal"] + list(ALTERNATIVE_GAITS.keys())