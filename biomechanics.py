import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional

# Pydantic модели данных

class SocketModel(BaseModel):
    '''Параметры гильзы протеза'''
    material: str = Field(default="carbon_fiber", description="Материал гильзы")
    critical_load: float = Field(default=3000, gt=0, description="Критическая нагрузка в Ньютонах")
    damping_coefficient: float = Field(default=0.85, ge=0, le=1, description="Коэффициент демпфирования")

    # Коэффициенты усталости (упрощенно для S-N кривой: S = a*(2N)^b)
    fatigue_intercept: float = Field(default=5000, description="Предел прочности при 1 цикле (Н)")
    fatigue_slope: float = Field(default=-0.1, description="Показатель наклона кривой усталости")

class RequestBiomech(BaseModel):
    '''Данные с фронтенда при запросе'''
    weight: float = Field(..., gt=0, lt=500, description="Вес человека в кг") #... => обязательное поле, greather than 0, less than 500
    height: float = Field(175, gt=100, lt=250, description="Рост в см")
    socket: SocketModel = Field(default_factory=SocketModel)
    movement_type: Literal["walking", "jump"] = Field(...) #Literal[...] - фикс.знач., причем д.б. одно из ...
    steps_per_day: int = Field(default=5000, ge=0)
    speed: Optional[float] = Field(None, gt=0, lt=15) #Optional[float] - ожидаем число, но если не придет - все ок
    jump_height: Optional[float] = Field(None, gt=0, lt=3)

class ResponseBiomech(BaseModel):
    """Ответ API с результатами анализа"""
    time_data: list[float]
    critical_load: float
    fx_data: list[float] 
    fy_data: list[float]
    fz_data: list[float]
    max_load: float
    risk_percentage: float
    recommendations: list[str] = []

# ===== РАСЧЕТНЫЕ КЛАССЫ =====

class AnalyseBiomech:
    """Класс для комплексного биомеханического анализа нагрузки"""
    
    def __init__(self, request: RequestBiomech):
        self.request = request
        self.g = 9.81

    def get_duration(self) -> float:
        """Рассчитывает длительность цикла движения"""
        if self.request.movement_type == "jump":
            height = self.request.jump_height or 0.5
            # Время полета: 2 * sqrt(2h/g)
            flight_time = 2 * np.sqrt(2 * height / self.g)
            # Добавляем время на подготовку и приземление (~0.3-0.5 сек)
            prep_time = 0.35
            return flight_time + prep_time
        
        height_m = self.request.height / 100
        stride_length = height_m * 0.43
        
        #ходьба
        speed = self.request.speed or 1.4
            
        return stride_length / speed

    def calculate_load_series(self, time_array: np.ndarray) -> np.ndarray:
        """Генерирует кривую нагрузки"""
        mass = self.request.weight
        duration = self.get_duration()
        
        if self.request.movement_type == "walking":
            return mass * self.g * (1.2 + 1.0 * np.abs(np.sin(2 * np.pi * time_array / duration)))
            
        else:  # jump - ДВУХГОРБЫЙ ГРАФИК
        # Параметры прыжка
            t_takeoff = duration * 0.35  # Отталкивание (35% времени)
            t_landing = duration * 0.65  # Приземление (65% времени)
            
            # Ширина импульсов
            width_takeoff = duration * 0.08
            width_landing = duration * 0.08
            
            # Амплитуды (в долях веса тела)
            # Отталкивание - активное усилие ~2.5-3x веса
            # Приземление - ударная нагрузка ~3-5x веса (сильнее)
            amplitude_takeoff = 2.5 * mass * self.g
            amplitude_landing = 4.0 * mass * self.g
            
            # Генерируем два пика (модифицированная гауссиана)
            takeoff_peak = amplitude_takeoff * np.exp(-((time_array - t_takeoff) ** 2) / (2 * width_takeoff ** 2))
            landing_peak = amplitude_landing * np.exp(-((time_array - t_landing) ** 2) / (2 * width_landing ** 2))
            
            # Суммируем пики
            load = takeoff_peak + landing_peak
            
            # Добавляем небольшой вес тела в промежутке (полетная фаза)
            # В полете нагрузка близка к 0, но добавим вес тела в начале и конце
            load = np.maximum(load, mass * self.g * 0.1)
        
            # Обнуляем после завершения цикла
            return np.where(time_array > duration, 0, load)

    def calculate_3d_load_series(self, time_array: np.ndarray):
        """Генерирует трехмерный вектор нагрузки (Fx, Fy, Fz)"""
        duration = self.get_duration()
        mass = self.request.weight
        g = self.g
        movement = self.request.movement_type
        
        # Fz - Вертикальная сила (всегда)
        fz = self.calculate_load_series(time_array)
        
        if movement == "jump":
            # Для прыжка - только вертикальная нагрузка, горизонтальные обнуляем
            fx = np.zeros_like(time_array)
            fy = np.zeros_like(time_array)
        else:
            # Для ходьбы и бега - оставляем горизонтальные силы
            fy = 0.2 * mass * g * np.sin(2 * np.pi * time_array / duration)
            fx = 0.05 * mass * g * np.cos(np.pi * time_array / duration)
        
        return fx, fy, fz

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

        # Советы по материалу (только по риску, без учета срока службы)
        if material == "thermoplastic" and risk > 70:
            recs.append("💡 СОВЕТ: Пластиковая гильза не справляется с вашей нагрузкой. Рекомендуется переход на карбон.")
        
        if material == "carbon_fiber" and risk < 30:
            recs.append("ℹ️ Запас прочности избыточен. Для снижения веса можно использовать более легкие материалы.")

        # Советы по типу движения
        if movement_type == "jump" and risk > 60:
            recs.append("🏃‍♂️ Прыжки создают высокую ударную нагрузку. Рекомендуется ограничить их частоту.")
        elif movement_type == "running" and risk > 60:
            recs.append("🏃‍♂️ При беге нагрузка выше нормы. Рассмотрите альтернативные виды активности.")

        return recs