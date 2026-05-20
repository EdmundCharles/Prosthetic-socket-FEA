import numpy as np
import rainflow

def reduce_tensor_to_scalar(stress_history_voigt, material_type="petg"):
    """
    ШАГ 1: РЕДУКЦИЯ ТЕНЗОРА.
    Переводит 3D-тензор напряжений, меняющийся во времени, в 1D-массив скаляров.
    
    ВХОД:
    - stress_history_voigt: numpy-массив формы (N_steps, 6). 
      Содержит напряжения для одного узла на каждом временном шаге в формате Voigt:
      [Sxx, Syy, Szz, Sxy, Syz, Sxz] - стандартный вывод CalculiX.
    - material_type: строка "petg" (Signed Von Mises) или "carbon" (Max Principal Stress).
    
    ВЫХОД:
    - 1D numpy-массив формы (N_steps,) с редуцированными напряжениями.
    """
    Sxx = stress_history_voigt[:, 0]
    Syy = stress_history_voigt[:, 1]
    Szz = stress_history_voigt[:, 2]
    Sxy = stress_history_voigt[:, 3]
    Syz = stress_history_voigt[:, 4]
    Sxz = stress_history_voigt[:, 5]

    if material_type.lower() == "petg":
        # 1. Вычисляем первый инвариант (след тензора) для определения знака
        I1 = Sxx + Syy + Szz
        
        # 2. Вычисляем стандартное напряжение по Мизесу
        # Формула: sqrt(0.5 * ((Sxx-Syy)^2 + (Syy-Szz)^2 + (Szz-Sxx)^2 + 6*(Sxy^2 + Syz^2 + Sxz^2)))
        vm_squared = 0.5 * ((Sxx - Syy)**2 + (Syy - Szz)**2 + (Szz - Sxx)**2 + 6 * (Sxy**2 + Syz**2 + Sxz**2))
        von_mises = np.sqrt(np.maximum(vm_squared, 0.0)) # maximum для защиты от микро-отрицательных чисел из-за float
        
        # 3. Присваиваем знак от I1
        signs = np.sign(I1)
        # Если I1 == 0, считаем знак положительным
        signs[signs == 0] = 1.0 
        
        return von_mises * signs

    elif material_type.lower() == "carbon":
        # Для расчета главных напряжений нужно собрать 3x3 матрицы для каждого шага
        N = stress_history_voigt.shape[0]
        tensors = np.zeros((N, 3, 3))
        
        tensors[:, 0, 0] = Sxx
        tensors[:, 1, 1] = Syy
        tensors[:, 2, 2] = Szz
        tensors[:, 0, 1] = tensors[:, 1, 0] = Sxy
        tensors[:, 1, 2] = tensors[:, 2, 1] = Syz
        tensors[:, 0, 2] = tensors[:, 2, 0] = Sxz
        
        # Вычисляем собственные значения (главные напряжения)
        # eigvalsh работает быстрее и точнее для симметричных матриц
        eigenvalues = np.linalg.eigvalsh(tensors) 
        
        # Находим максимальное главное напряжение (наибольшее растяжение)
        max_principal = np.max(eigenvalues, axis=1)
        return max_principal
        
    else:
        raise ValueError("Неизвестный тип материала. Выберите 'petg' или 'carbon'.")


def count_rainflow_cycles(stress_1d):
    """
    ШАГ 2: RAINFLOW COUNTING.
    Извлекает замкнутые циклы напряжений из временного ряда.
    
    ВХОД:
    - stress_1d: 1D numpy-массив напряжений (результат функции reduce_tensor_to_scalar).
    
    ВЫХОД:
    - cycles: список словарей, где каждый элемент содержит:
      {'amplitude': амплитуда цикла, 'mean': среднее напряжение, 'count': 0.5 или 1.0}
      (0.5 - это полуцикл, 1.0 - полный цикл).
    """
    # Экстракция экстремумов (пиков и впадин) - rainflow работает именно с ними
    # Библиотека rainflow.extract возвращает кортеж: (размах, среднее, кол-во_циклов, start_idx, end_idx)
    cycles_raw = rainflow.extract(stress_1d)
    
    cycles = []
    for rng, mean, count, i_start, i_end in cycles_raw:
        cycles.append({
            "amplitude": rng / 2.0, # Размах (range) делится пополам, чтобы получить амплитуду
            "mean": mean,
            "count": count # Будет 0.5 или 1.0
        })
        
    return cycles


def correct_mean_stress(cycles, ultimate_tensile_strength, method="goodman"):
    """
    ШАГ 3: КОРРЕКЦИЯ СРЕДНИХ НАПРЯЖЕНИЙ.
    Приводит циклы с ненулевым средним напряжением к эквивалентным симметричным циклам.
    
    ВХОД:
    - cycles: список словарей (выход count_rainflow_cycles).
    - ultimate_tensile_strength (UTS): предел прочности материала (в тех же единицах, что и напряжения, например МПа).
    - method: "goodman" (линейная) или "gerber" (параболическая).
    
    ВЫХОД:
    - эквивалентные циклы (тот же формат, но mean=0, а amplitude пересчитана).
    """
    eq_cycles = []
    
    for cycle in cycles:
        amp = cycle["amplitude"]
        mean = cycle["mean"]
        count = cycle["count"]
        
        # Если напряжение сжатия, оно меньше вредит (или не вредит). 
        # Консервативный подход в инженерии: для сжатия эквивалентная амплитуда равна исходной.
        if mean <= 0:
            eq_amp = amp
        else:
            if method.lower() == "goodman":
                # Формула Гудмана: S_eq = S_a / (1 - S_m / UTS)
                # Защита от деления на ноль или отрицательных значений (если среднее напряжение выше предела прочности)
                denominator = 1.0 - (mean / ultimate_tensile_strength)
                eq_amp = amp / denominator if denominator > 0 else float('inf')
                
            elif method.lower() == "gerber":
                # Формула Гербера: S_eq = S_a / (1 - (S_m / UTS)^2)
                denominator = 1.0 - (mean / ultimate_tensile_strength)**2
                eq_amp = amp / denominator if denominator > 0 else float('inf')
            else:
                raise ValueError("Неизвестный метод коррекции. Выберите 'goodman' или 'gerber'.")
                
        eq_cycles.append({
            "amplitude": eq_amp,
            "mean": 0.0,
            "count": count
        })
        
    return eq_cycles


def calculate_miners_rule(eq_cycles, fatigue_intercept, fatigue_slope):
    """
    ШАГ 4: ПРАВИЛО МАЙНЕРА.
    Суммирует повреждения от всех эквивалентных циклов по S-N кривой (уравнение Баскина).
    Уравнение Баскина: S_a = A * (2N)^b, где A - intercept, b - slope.
    
    ВХОД:
    - eq_cycles: список эквивалентных циклов (выход correct_mean_stress).
    - fatigue_intercept: предел прочности при 1 цикле (параметр A из вашей SocketModel).
    - fatigue_slope: показатель наклона кривой (параметр b из SocketModel, обычно отрицательный, например -0.1).
    
    ВЫХОД:
    - damage: накопленное усталостное повреждение (D). 
      Если D >= 1.0, произойдет разрушение.
    """
    damage = 0.0
    
    for cycle in eq_cycles:
        eq_amp = cycle["amplitude"]
        n_applied = cycle["count"]
        
        if eq_amp <= 0:
            continue
            
        # Вычисляем количество циклов до разрушения (N_fail) для данной амплитуды
        # Решаем уравнение Баскина относительно N:
        # 2 * N_fail = (S_a / A)^(1/b) -> N_fail = 0.5 * (S_a / A)^(1/b)
        
        try:
            # Избегаем деления на ноль или логарифмов от отрицательных чисел
            cycles_to_failure = 0.5 * (eq_amp / fatigue_intercept) ** (1.0 / fatigue_slope)
            
            # Если cycles_to_failure огромное (ниже предела выносливости), урон стремится к нулю
            if cycles_to_failure > 0:
                damage += n_applied / cycles_to_failure
            else:
                damage = float('inf') # Мгновенное разрушение (амплитуда выше предела)
        except ZeroDivisionError:
            damage = float('inf')
            
    return damage

# =====================================================================
# ФУНКЦИЯ-ОРКЕСТРАТОР ДЛЯ УДОБСТВА
# =====================================================================
def analyze_node_fatigue(stress_history_voigt, material_params):
    """
    Объединяет все 4 шага для анализа одного конкретного узла МКЭ-сетки.
    """
    # 1. Редукция
    stress_1d = reduce_tensor_to_scalar(stress_history_voigt, material_params["type"])
    
    # 2. Метод Дождя
    cycles = count_rainflow_cycles(stress_1d)
    
    # 3. Коррекция
    eq_cycles = correct_mean_stress(
        cycles, 
        ultimate_tensile_strength=material_params["uts"], 
        method="goodman"
    )
    
    # 4. Повреждение
    damage = calculate_miners_rule(
        eq_cycles, 
        fatigue_intercept=material_params["fatigue_intercept"], 
        fatigue_slope=material_params["fatigue_slope"]
    )
    
    return damage
