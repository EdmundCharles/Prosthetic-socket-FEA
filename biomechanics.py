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
    thigh_girth: float = Field(..., gt=20, lt=100, description="Обхват бедра в см")
    socket: SocketModel = Field(default_factory=SocketModel)
    movement_type: Literal["walking", "running", "jump"] = Field(...) #Literal[...] - фикс.знач., причем д.б. одно из ...
    steps_per_day: int = Field(default=5000, ge=0)
    speed: Optional[float] = Field(None, gt=0, lt=15) #Optional[float] - ожидаем число, но если не придет - все ок
    jump_height: Optional[float] = Field(None, gt=0, lt=3)

class ResponseBiomech(BaseModel):
    """Ответ API с результатами анализа"""
    time_data: list[float]
    load_data: list[float]
    critical_load: float
    max_load: float
    risk_percentage: float
    service_life: float
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
            return 2 * np.sqrt(2 * height / self.g)
        
        height_m = self.request.height / 100
        stride_length = height_m * 0.43
        
        if self.request.movement_type == "walking":
            speed = self.request.speed or 1.4
        else: # running
            speed = self.request.speed or 3.0
            
        return stride_length / speed

    def calculate_load_series(self, time_array: np.ndarray) -> np.ndarray:
        """Генерирует кривую нагрузки"""
        mass = self.request.weight
        duration = self.get_duration()
        
        if self.request.movement_type == "walking":
            return mass * self.g * (1.2 + 1.0 * np.abs(np.sin(2 * np.pi * time_array / duration)))
            
        elif self.request.movement_type == "running":
            t_mod = (time_array % duration) / duration
            load = mass * self.g * (2.5 + 3.5 * np.exp(-8 * t_mod) * np.sin(np.pi * t_mod))
            return np.maximum(load, mass * self.g * 1.2)
            
        else:  # jump
            impact_time = duration / 2
            load = mass * self.g * (1 + 3 * np.exp(-50 * (time_array - impact_time)**2))
            return np.where(time_array > duration, 0, load)

    def calculate_service_life(self, max_load: float) -> float:
        """Прогноз срока службы по уравнению Баскина N = (Load / A)^(1/b)"""
        socket = self.request.socket
        if max_load >= socket.critical_load:
            return 0
        try:
            max_cycles = 0.5 * (max_load / socket.fatigue_intercept) ** (1 / socket.fatigue_slope)
            years = max_cycles / (self.request.steps_per_day * 365)
            return round(min(years, 20), 1)
        except:
            return 0

    def generate_recommendations(self, max_load: float, risk: float, service_life: float) -> list[str]:
        """Формирует список советов на основе расчетов"""
        recs = []
        material = self.request.socket.material
        movement_type = self.request.movement_type
    
        # Анализ статического риска
        if risk > 80 and risk < 100:
            recs.append("⚠️ ВНИМАНИЕ: Текущая нагрузка близка к критической. Избегайте резких прыжков.")
        if risk == 100:
            recs.append("🔴 Превышен предел прочности")
        
        # Анализ срока службы
        if service_life < 1.5:
            recs.append("🔴 Срок службы критически мал. Рекомендуется сменить материал гильзы на более прочный.")
        elif service_life < 5:
            recs.append("🟡 Умеренный износ. Рекомендуется плановое ТО гильзы раз в полгода.")
        else:
            recs.append("🟢 Нагрузка в норме. Текущий режим активности безопасен для изделия.")

        # Советы по материалу
        if material == "thermoplastic" and (risk > 80 or service_life < 2):
            recs.append("💡 СОВЕТ: Пластиковая гильза не справляется с вашей нагрузкой. Переход на карбон увеличит срок службы в 5-10 раз.")
        
        if material == "carbon_fiber" and service_life > 15 and risk < 30:
            recs.append("ℹ️ Запас прочности избыточен. Для этого уровня активности можно использовать более дешевый термопластик.")

        # Специфические советы по типу движения
        if movement_type == "running" and risk > 60:
            recs.append("🏃‍♂️ При беге наблюдается высокая ударная нагрузка. Рассмотрите установку стопы с амортизатором.")
        
        if service_life > 10 and risk < 40:
            recs.append("✅ У вас большой запас прочности. Можно рассмотреть облегчение гильзы для комфорта.")

        return recs
