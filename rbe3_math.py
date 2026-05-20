import numpy as np

def distribute_rbe3(master_coord, force_vector, slave_coords):
    slave_coords = np.array(slave_coords)
    F_master = np.array(force_vector)
    
    # Центроид ведомых узлов
    rc = np.mean(slave_coords, axis=0)
    
    # Момент относительно центроида
    r_master = np.array(master_coord) - rc
    Mc = np.cross(r_master, F_master)
    
    # Векторы позиций относительно центроида
    r = slave_coords - rc
    
    # Тензор инерции облака точек
    I = np.zeros((3, 3))
    for ri in r:
        I += np.eye(3) * np.dot(ri, ri) - np.outer(ri, ri)
        
    # Вычисляем псевдо-угловое ускорение
    alpha = np.linalg.solve(I, Mc)
    
    # Распределяем силы
    N = len(slave_coords)
    F_distributed = np.zeros_like(slave_coords)
    for i, ri in enumerate(r):
        F_distributed[i] = F_master / N + np.cross(alpha, ri)
        
    return F_distributed

# Тест
master = [0.5, 0.5, 10.0]
force = [100.0, 0.0, 0.0]
slaves = [[0,0,1], [1,0,1], [1,1,1], [0,1,1]]
F = distribute_rbe3(master, force, slaves)
print("Forces:\n", F)
print("Sum of forces:", np.sum(F, axis=0))

rc = np.mean(slaves, axis=0)
total_moment = np.zeros(3)
for i, s in enumerate(slaves):
    total_moment += np.cross(np.array(s) - rc, F[i])
print("Sum of moments:", total_moment)
print("Expected moment:", np.cross(np.array(master)-rc, force))
