import numpy as np
import rainflow

def extract_fdm_stresses(stress_history_voigt):
    Sxx = stress_history_voigt[:, 0]
    Syy = stress_history_voigt[:, 1]
    Szz = stress_history_voigt[:, 2]
    Sxy = stress_history_voigt[:, 3]
    
    center = (Sxx + Syy) / 2.0
    radius = np.sqrt(((Sxx - Syy) / 2.0)**2 + Sxy**2)
    in_plane_stress = center + radius
    interlayer_stress = Szz
    return in_plane_stress, interlayer_stress

def count_rainflow_cycles(stress_1d):
    cycles_raw = rainflow.extract_cycles(stress_1d)
    cycles = []
    for rng, mean, count, i_start, i_end in cycles_raw:
        cycles.append({
            "amplitude": rng / 2.0, 
            "mean": mean,
            "count": count           
        })
    return cycles

def correct_mean_stress(cycles, ultimate_tensile_strength, method="goodman"):
    eq_cycles = []
    for cycle in cycles:
        amp = cycle["amplitude"]
        mean = cycle["mean"]
        count = cycle["count"]
        
        if mean <= 0:
            eq_amp = amp
        else:
            if method.lower() == "goodman":
                denominator = 1.0 - (mean / ultimate_tensile_strength)
                eq_amp = amp / denominator if denominator > 0 else float('inf')
            elif method.lower() == "gerber":
                denominator = 1.0 - (mean / ultimate_tensile_strength)**2
                eq_amp = amp / denominator if denominator > 0 else float('inf')
            else:
                raise ValueError("Неизвестный метод")
                
        eq_cycles.append({
            "amplitude": eq_amp,
            "mean": 0.0,
            "count": count
        })
    return eq_cycles

def calculate_miners_rule(eq_cycles, fatigue_intercept, fatigue_slope):
    damage = 0.0
    for cycle in eq_cycles:
        eq_amp = cycle["amplitude"]
        n_applied = cycle["count"]
        if eq_amp <= 0:
            continue
        try:
            cycles_to_failure = 0.5 * (eq_amp / fatigue_intercept) ** (1.0 / fatigue_slope)
            if cycles_to_failure > 0:
                damage += n_applied / cycles_to_failure
            else:
                damage = float('inf')
        except ZeroDivisionError:
            damage = float('inf')
    return damage

def analyze_fdm_node_fatigue(stress_history_voigt, mat_in_plane, mat_interlayer, correction_method="goodman"):
    stress_ip, stress_z = extract_fdm_stresses(stress_history_voigt)
    
    cycles_ip = count_rainflow_cycles(stress_ip)
    eq_cycles_ip = correct_mean_stress(cycles_ip, ultimate_tensile_strength=mat_in_plane["uts"], method=correction_method)
    damage_ip = calculate_miners_rule(eq_cycles_ip, fatigue_intercept=mat_in_plane["fatigue_intercept"], fatigue_slope=mat_in_plane["fatigue_slope"])
    
    cycles_z = count_rainflow_cycles(stress_z)
    eq_cycles_z = correct_mean_stress(cycles_z, ultimate_tensile_strength=mat_interlayer["uts"], method=correction_method)
    damage_z = calculate_miners_rule(eq_cycles_z, fatigue_intercept=mat_interlayer["fatigue_intercept"], fatigue_slope=mat_interlayer["fatigue_slope"])
    
    critical_mode = "Отрыв слоев (Z-Ось)" if damage_z > damage_ip else "Разрыв нити (XY-Ось)"
    max_damage = max(damage_ip, damage_z)
    
    return {
        "total_damage": max_damage,
        "critical_mode": critical_mode,
        "damage_ip": damage_ip,
        "damage_z": damage_z
    }
