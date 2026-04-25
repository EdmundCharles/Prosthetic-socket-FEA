import trimesh
import gmsh
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve


def generate_volumetric_mesh(file_path: str, mesh_size: float = 8.0):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.merge(file_path)
    
    # Задаем угол толерантности для классификации поверхностей (40 градусов)
    angle = 40 * np.pi / 180
    gmsh.model.mesh.classifySurfaces(angle, True, True, angle)
    gmsh.model.mesh.createGeometry()
    
    surfaces = gmsh.model.getEntities(2)
    surface_loop = gmsh.model.geo.addSurfaceLoop([s[1] for s in surfaces])
    gmsh.model.geo.addVolume([surface_loop])
    gmsh.model.geo.synchronize()

    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
    gmsh.option.setNumber("Mesh.ElementOrder", 1) # Линейные тетраэдры

    gmsh.model.mesh.generate(3)

    nodeTags, nodeCoords, _ = gmsh.model.mesh.getNodes()
    nodes = np.array(nodeCoords).reshape(-1, 3)
    
    elemTypes, elemTags, elemNodeTags = gmsh.model.mesh.getElements(dim=3)
    tet_nodes = []
    for i, etype in enumerate(elemTypes):
        if etype == 4:
            tet_nodes = np.array(elemNodeTags[i]).reshape(-1, 4) - 1 

    gmsh.finalize()
    return nodes, tet_nodes

def apply_boundary_conditions(nodes):
    z_coords = nodes[:, 2]
    z_min, z_max = np.min(z_coords), np.max(z_coords)
    
    # Узлы заделки (дно) и нагрузки (верх)
    bottom_nodes = np.where(z_coords <= z_min + 5.0)[0]
    top_nodes = np.where(z_coords >= z_max - 5.0)[0]
    
    return bottom_nodes, top_nodes

def solve_fem_system(nodes, elements, bottom_nodes, top_nodes, load_newtons, offset_x, offset_y):
    # Физика материала (FGF пластик)
    E = 2100.0   # МПа
    nu = 0.35    # Коэффициент Пуассона

    num_nodes = len(nodes)
    num_physical_dofs = 3 * num_nodes
    
    # +1 Мастер-узел (6 степеней свободы: 3 перемещения, 3 поворота)
    master_dof_start = num_physical_dofs
    total_dofs = num_physical_dofs + 6
    
    # Матрица упругости D
    coeff = E / ((1 + nu) * (1 - 2 * nu))
    D = coeff * np.array([
        [1-nu,   nu,   nu,          0,          0,          0],
        [  nu, 1-nu,   nu,          0,          0,          0],
        [  nu,   nu, 1-nu,          0,          0,          0],
        [   0,    0,    0, (1-2*nu)/2,          0,          0],
        [   0,    0,    0,          0, (1-2*nu)/2,          0],
        [   0,    0,    0,          0,          0, (1-2*nu)/2]
    ])

    row_indices, col_indices, data_values = [], [], []

    # 1. Сборка матрицы упругости тетраэдров (как было)
    for elem in elements:
        coords = nodes[elem]
        M = np.ones((4, 4))
        M[:, 1:4] = coords
        try:
            Minv = np.linalg.inv(M)
            volume = np.abs(np.linalg.det(M)) / 6.0
        except: continue
            
        b, c, d = Minv[1, :], Minv[2, :], Minv[3, :]
        B = np.zeros((6, 12))
        for i in range(4):
            B[0, i*3], B[1, i*3+1], B[2, i*3+2] = b[i], c[i], d[i]
            B[3, i*3], B[3, i*3+1] = c[i], b[i]
            B[4, i*3+1], B[4, i*3+2] = d[i], c[i]
            B[5, i*3], B[5, i*3+2] = d[i], b[i]
            
        Ke = B.T @ D @ B * volume
        elem_dofs = np.repeat(elem * 3, 3) + np.tile([0, 1, 2], 4)
        grid_row, grid_col = np.meshgrid(elem_dofs, elem_dofs, indexing='ij')
        row_indices.extend(grid_row.flatten())
        col_indices.extend(grid_col.flatten())
        data_values.extend(Ke.flatten())

    # =========================================================
    # 2. RBE2 ЭЛЕМЕНТ: ЖЕСТКАЯ КИНЕМАТИЧЕСКАЯ СВЯЗЬ (ГОСТ 10328)
    # =========================================================
    top_coords = nodes[top_nodes]
    cx = np.mean(top_coords[:, 0])
    cy = np.mean(top_coords[:, 1])
    cz = np.max(nodes[:, 2]) + 50.0  # Виртуальный адаптер вынесен на 50 мм вверх
    
    # Координаты Мастер-узла (точка приложения силы пресса)
    xm = cx + offset_x
    ym = cy + offset_y
    zm = cz
    
    PENALTY_RBE = 1e10 * E  # Штрафная жесткость (имитация абсолютно жесткого металла)

    for node_idx in top_nodes:
        x, y, z = nodes[node_idx]
        dx, dy, dz = x - xm, y - ym, z - zm
        
        # Матрица связей C (3 уравнения на 9 степеней свободы: 3 для Slave, 6 для Master)
        # Порядок DOF: [u_sx, u_sy, u_sz,  u_mx, u_my, u_mz,  th_mx, th_my, th_mz]
        C = np.array([
            [ 1,  0,  0,  -1,  0,  0,    0,  -dz,   dy],
            [ 0,  1,  0,   0, -1,  0,   dz,    0,  -dx],
            [ 0,  0,  1,   0,  0, -1,  -dy,   dx,    0]
        ])
        
        # Штрафная матрица жесткости для конкретной связи
        K_pen = PENALTY_RBE * (C.T @ C)
        
        # Индексы DOF для сборки в глобальную матрицу
        global_dofs = [
            node_idx*3, node_idx*3+1, node_idx*3+2,                  # Slave DOFs
            master_dof_start, master_dof_start+1, master_dof_start+2,# Master Translations
            master_dof_start+3, master_dof_start+4, master_dof_start+5 # Master Rotations
        ]
        
        for r in range(9):
            for c in range(9):
                row_indices.append(global_dofs[r])
                col_indices.append(global_dofs[c])
                data_values.append(K_pen[r, c])

    # 3. Сборка глобальной расширенной матрицы
    K = sp.coo_matrix((data_values, (row_indices, col_indices)), shape=(total_dofs, total_dofs)).tocsr()
    
    # 4. Вектор нагрузок (Сила прикладывается ТОЛЬКО к Мастер-узлу)
    F = np.zeros(total_dofs)
    # Сила направлена вниз по оси Z
    F[master_dof_start + 2] = -load_newtons 

    # 5. Граничные условия (Заделка дна)
    PENALTY_BC = 1e16
    fixed_dofs = []
    for node in bottom_nodes: 
        fixed_dofs.extend([node*3, node*3+1, node*3+2])
    K[fixed_dofs, fixed_dofs] += PENALTY_BC
    
    # 6. Решение СЛАУ
    u = spsolve(K, F)
    
    # Отсекаем фиктивные DOF Мастер-узла, нас интересуют только физические перемещения гильзы
    displacements = u[:num_physical_dofs].reshape((-1, 3))
    disp_mag = np.linalg.norm(displacements, axis=1)
    
    return nodes.tolist(), disp_mag.tolist(), np.max(disp_mag)

def process_and_simulate(file_path: str, load_newtons: float, offset_x: float, offset_y: float):
    nodes, elements = generate_volumetric_mesh(file_path)
    bottom_idx, top_idx = apply_boundary_conditions(nodes)
    
    nodes_list, disp_list, max_disp = solve_fem_system(
        nodes, elements, bottom_idx, top_idx, 
        float(load_newtons), float(offset_x), float(offset_y)
    )
    
    # Возвращаем также координаты для отрисовки векторов
    return {
        "status": "success",
        "nodes_count": len(nodes),
        "max_stress": round(max_disp, 3),
        "fem_nodes": nodes_list,
        "fem_values": disp_list,
        "bottom_coords": nodes[bottom_idx].tolist(),
        "top_coords": nodes[top_idx].tolist()
    }