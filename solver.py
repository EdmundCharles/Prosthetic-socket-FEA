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
    """
    Математическое ядро МКЭ. 
    Теперь принимает offset_x и offset_y для реализации ГОСТ 10328.
    """
    # Физика материала (FGF пластик, примерные значения)
    E = 2100.0   # МПа
    nu = 0.35    # Коэффициент Пуассона

    num_nodes = len(nodes)
    num_dofs = 3 * num_nodes
    
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
        row_indices.extend(grid_row.flatten()); col_indices.extend(grid_col.flatten()); data_values.extend(Ke.flatten())

    K = sp.coo_matrix((data_values, (row_indices, col_indices)), shape=(num_dofs, num_dofs)).tocsr()
    
    # РАСЧЕТ НАГРУЗКИ ПО ГОСТ (Внецентренное сжатие)
    F = np.zeros(num_dofs)
    top_coords = nodes[top_nodes]
    cx, cy = np.mean(top_coords[:, 0]), np.mean(top_coords[:, 1])
    
    dx, dy = top_coords[:, 0] - cx, top_coords[:, 1] - cy
    I_x, I_y = np.sum(dy**2), np.sum(dx**2)
    M_y, M_x = load_newtons * offset_x, load_newtons * offset_y
    
    for i, node_idx in enumerate(top_nodes):
        dof_z = node_idx * 3 + 2
        f_axial = -load_newtons / len(top_nodes)
        f_bend_x = (M_x * dy[i]) / I_x if I_x > 0 else 0
        f_bend_y = -(M_y * dx[i]) / I_y if I_y > 0 else 0
        F[dof_z] = f_axial + f_bend_x + f_bend_y

    # Граничные условия (Заделка дна)
    PENALTY = 1e16
    fixed_dofs = []
    for node in bottom_nodes: fixed_dofs.extend([node*3, node*3+1, node*3+2])
    K[fixed_dofs, fixed_dofs] += PENALTY
    
    u = spsolve(K, F)
    displacements = u.reshape((-1, 3))
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