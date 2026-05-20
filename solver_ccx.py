import os
import subprocess
import numpy as np
import pyvista as pv
import gmsh
import math
import time
from scipy.spatial import cKDTree

# ==========================================
# БЛОК 1 и 2 ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ ДО generate_inp
# ==========================================
def prepare_volume_mesh(stl_path, target_element_size=5.0):
    # Код из вашей версии...
    print("Оптимизация STL через PyVista...")
    mesh = pv.read(stl_path)
    if mesh.n_points > 100000:
        reduction_factor = 1.0 - (100000 / mesh.n_points)
        mesh = mesh.decimate_pro(reduction_factor, preserve_topology=True)
        mesh = mesh.clean()
    clean_stl_path = "temp_clean.stl"
    mesh.save(clean_stl_path)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0) 
    gmsh.merge(clean_stl_path)
    gmsh.model.mesh.classifySurfaces(40 * math.pi / 180, True, True, math.pi)
    gmsh.model.mesh.createGeometry()
    gmsh.model.geo.synchronize()
    s_entities = gmsh.model.getEntities(2)
    s_tags = [tag for dim, tag in s_entities]
    sl = gmsh.model.geo.addSurfaceLoop(s_tags)
    gmsh.model.geo.addVolume([sl])
    gmsh.model.geo.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMin", 1) 
    gmsh.option.setNumber("Mesh.MeshSizeMax", target_element_size)
    gmsh.option.setNumber("Mesh.CharacteristicLengthFromCurvature", 1)
    gmsh.option.setNumber("Mesh.MinimumElementsPerTwoPi", 10)
    gmsh.option.setNumber("Mesh.Optimize", 1)
    gmsh.option.setNumber("Mesh.OptimizeNetgen", 1) 
    gmsh.model.mesh.generate(3)
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes_raw = np.array(node_coords).reshape(-1, 3)
    tag_to_idx = {tag: idx for idx, tag in enumerate(node_tags)}
    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(dim=3)
    elements_raw = []
    for etype, enode_tags in zip(elem_types, elem_node_tags):
        if etype == 4: 
            nodes_per_elem = np.array(enode_tags).reshape(-1, 4)
            mapped = np.array([tag_to_idx.get(t, -1) for t in nodes_per_elem.flatten()]).reshape(-1, 4)
            valid_mask = (mapped != -1).all(axis=1)
            elements_raw.extend(mapped[valid_mask])
    gmsh.finalize()
    if os.path.exists(clean_stl_path): os.remove(clean_stl_path)
    elements_raw = np.array(elements_raw)
    used_nodes = np.unique(elements_raw)
    clean_nodes = nodes_raw[used_nodes]
    clean_nodes = np.nan_to_num(clean_nodes, nan=0.0)
    mapping = np.full(len(nodes_raw), -1, dtype=int)
    mapping[used_nodes] = np.arange(len(used_nodes))
    clean_elements = mapping[elements_raw]
    return clean_nodes, clean_elements

def get_bottom_nodes(nodes, tolerance=5.0):
    min_z = np.min(nodes[:, 2])
    return np.where(nodes[:, 2] <= min_z + tolerance)[0].tolist()

def get_internal_slave_nodes(nodes, elements, depth=150.0):
    cells = np.hstack((np.full((len(elements), 1), 4), elements)).astype(int).flatten()
    celltypes = np.full(len(elements), pv.CellType.TETRA)
    grid = pv.UnstructuredGrid(cells, celltypes, nodes)
    surf = grid.extract_surface(algorithm='dataset_surface')
    surf = surf.compute_normals(cell_normals=False, point_normals=True, auto_orient_normals=True)
    surf_points, surf_normals = surf.points, surf['Normals']
    max_z = np.max(nodes[:, 2])
    top_mask = surf_points[:, 2] >= (max_z - depth)
    if not np.any(top_mask): return []
    cx, cy = np.mean(surf_points[top_mask, 0]), np.mean(surf_points[top_mask, 1])
    internal_coords = []
    for i in range(len(surf_points)):
        if not top_mask[i]: continue
        p, n = surf_points[i], surf_normals[i]
        vec_to_point = np.array([p[0] - cx, p[1] - cy, 0.0])
        norm_vec = np.linalg.norm(vec_to_point)
        if norm_vec < 1e-5: continue
        vec_to_point = vec_to_point / norm_vec
        n_xy = np.array([n[0], n[1], 0.0])
        norm_n = np.linalg.norm(n_xy)
        if norm_n > 1e-5:
            n_xy = n_xy / norm_n
            if np.dot(vec_to_point, n_xy) < -0.05: internal_coords.append(p)
    if not internal_coords: return []
    tree = cKDTree(nodes)
    _, slave_indices = tree.query(internal_coords)
    unique_slaves = list(set(slave_indices.tolist()))
    return unique_slaves

def get_gost_load_vector(force_mag, condition, z_top, z_bottom, cx, cy):
    gost_10328 = {
        "I":  {"PT": [-35.0, 10.0], "PB": [15.0, -10.0]}, 
        "II": {"PT": [25.0, -10.0], "PB": [115.0, 40.0]}  
    }
    data = gost_10328[condition]
    pt_x, pt_y = cx + data["PT"][0], cy + data["PT"][1]
    pb_x, pb_y = cx + data["PB"][0], cy + data["PB"][1]
    dx, dy, dz = pb_x - pt_x, pb_y - pt_y, z_bottom - z_top
    length = np.sqrt(dx**2 + dy**2 + dz**2)
    fx = force_mag * (dx / length)
    fy = force_mag * (dy / length)
    fz = force_mag * (dz / length)
    return [pt_x, pt_y, z_top + 50.0], [fx, fy, fz]

# ==========================================
# ОБНОВЛЕНИЕ: ВЫВОД НАПРЯЖЕНИЙ В INP
# ==========================================
def generate_inp(nodes, elements, bottom_nodes, top_nodes, force_vector, master_coords, material_type="petg_ortho", job_name="job"):
    with open(f"{job_name}.inp", "w") as f:
        f.write("*HEADING\nFGF Socket FEA\n*NODE, NSET=Nall\n")
        for i, (x, y, z) in enumerate(nodes): f.write(f"{i+1}, {x:.4f}, {y:.4f}, {z:.4f}\n")
        f.write("*ELEMENT, TYPE=C3D4, ELSET=Eall\n")
        for i, el in enumerate(elements): f.write(f"{i+1}, {el[0]+1}, {el[1]+1}, {el[2]+1}, {el[3]+1}\n")

        def write_nset(name, indices):
            f.write(f"*NSET, NSET={name}\n")
            for i in range(0, len(indices), 10): f.write(", ".join(map(lambda x: str(x+1), indices[i:i+10])) + "\n")

        write_nset("BottomNodes", bottom_nodes)
        write_nset("TopNodes", top_nodes)

        f.write("*MATERIAL, NAME=FGF_PETG\n")
        if material_type == "petg_ortho":
            f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
            f.write("2200.0, 2200.0, 1500.0, 0.38, 0.38, 0.38, 800.0, 550.0,\n550.0\n")
        else:
            f.write("*ELASTIC\n2100.0, 0.38\n")
            
        f.write("*SOLID SECTION, ELSET=Eall, MATERIAL=FGF_PETG\n")
        f.write("*STEP\n*STATIC\n*BOUNDARY\nBottomNodes, 1, 3, 0.0\n")
        
        # --- АНАЛИТИЧЕСКИЙ RBE3 ---
        # Распределяем силу и момент программно, так как CalculiX падает из-за лимита на размер MPC (12000 узлов)
        slave_coords = np.array([nodes[n] for n in top_nodes])
        rc = np.mean(slave_coords, axis=0)
        r_master = np.array(master_coords) - rc
        Mc = np.cross(r_master, force_vector)
        
        r = slave_coords - rc
        I = np.zeros((3, 3))
        for ri in r:
            I += np.eye(3) * np.dot(ri, ri) - np.outer(ri, ri)
            
        alpha = np.linalg.solve(I, Mc)
        
        f.write("*CLOAD\n")
        N_slaves = len(top_nodes)
        for i, n_idx in enumerate(top_nodes):
            F_i = np.array(force_vector) / N_slaves + np.cross(alpha, r[i])
            if abs(F_i[0]) > 1e-5: f.write(f"{n_idx+1}, 1, {F_i[0]:.5f}\n")
            if abs(F_i[1]) > 1e-5: f.write(f"{n_idx+1}, 2, {F_i[1]:.5f}\n")
            if abs(F_i[2]) > 1e-5: f.write(f"{n_idx+1}, 3, {F_i[2]:.5f}\n")
        
        
        # Запрашиваем U (перемещения) и S (напряжения, усредненные по узлам)
        f.write("*NODE PRINT, NSET=Nall\nU\n")
        f.write("*EL PRINT, ELSET=Eall, POSITION=AVERAGED AT NODES\nS\n")
        f.write("*END STEP\n")

def run_ccx(job_name="job"):
    my_env = os.environ.copy()
    my_env["OMP_NUM_THREADS"] = "6"
    ccx_path = "/opt/homebrew/bin/ccx_2.23"
    process = subprocess.run([ccx_path, "-i", job_name], env=my_env, capture_output=True, text=True)
    if process.returncode != 0 or not os.path.exists(f"{job_name}.dat"):
        raise RuntimeError("КРИТИЧЕСКИЙ СБОЙ CalculiX")
    return True

# ==========================================
# ОБНОВЛЕНИЕ: ПАРСИНГ ТЕНЗОРОВ
# ==========================================
def parse_dat(num_nodes, elements, job_name="job"):
    displacements = np.zeros((num_nodes, 3))
    stresses = np.zeros((num_nodes, 6))
    node_stress_count = np.zeros(num_nodes)

    with open(f"{job_name}.dat", 'r') as f: 
        lines = f.readlines()
    
    # 1. Перемещения
    start_idx_disp = next((i for i, line in enumerate(lines) if "displacements" in line), -1) + 2
    if start_idx_disp > 1:
        for line in lines[start_idx_disp:]:
            if not line.strip(): break
            parts = line.split()
            if len(parts) >= 4 and int(parts[0])-1 < num_nodes: 
                displacements[int(parts[0])-1] = [float(parts[1]), float(parts[2]), float(parts[3])]
                
    # 2. Напряжения
    start_idx_stress = next((i for i, line in enumerate(lines) if "stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz)" in line), -1)
    if start_idx_stress != -1:
        start_idx_stress += 3
        for line in lines[start_idx_stress:]:
            if not line.strip(): break
            parts = line.split()
            if len(parts) >= 8: 
                elem_idx = int(parts[0]) - 1
                if elem_idx < len(elements):
                    elem_nodes = elements[elem_idx]
                    sxx, syy, szz = float(parts[2]), float(parts[3]), float(parts[4])
                    sxy, sxz, syz = float(parts[5]), float(parts[6]), float(parts[7])
                    for node_idx in elem_nodes:
                        stresses[node_idx] += [sxx, syy, szz, sxy, syz, sxz]
                        node_stress_count[node_idx] += 1

    valid_nodes = node_stress_count > 0
    stresses[valid_nodes] = stresses[valid_nodes] / node_stress_count[valid_nodes][:, None]

    # Напряжение по Мизесу
    Sxx, Syy, Szz = stresses[:,0], stresses[:,1], stresses[:,2]
    Sxy, Syz, Sxz = stresses[:,3], stresses[:,4], stresses[:,5]
    vm_squared = 0.5 * ((Sxx - Syy)**2 + (Syy - Szz)**2 + (Szz - Sxx)**2 + 6 * (Sxy**2 + Syz**2 + Sxz**2))
    von_mises = np.sqrt(np.maximum(vm_squared, 0.0))
    
    # Фильтруем сингулярности: берем 99-й перцентиль Мизеса как критическое напряжение.
    # Это отсекает локальные пики из-за вырожденных элементов и точечных нагрузок.
    p99_stress = float(np.percentile(von_mises, 99.0))
    critical_node_idx = int(np.argmin(np.abs(von_mises - p99_stress)))
    
    return {
        "displacements": displacements.tolist(),
        "stresses_vm": von_mises.tolist(),
        "max_stress": p99_stress,
        "critical_node_idx": critical_node_idx,
        "critical_stress_voigt": stresses[critical_node_idx].tolist()
    }

def process_socket_analysis(stl_path, load_newtons, condition="II", mesh_size=5.0, search_depth=150.0, material="petg_ortho"):
    job_name, start_time = "socket_analysis", time.time()
    nodes, elements = prepare_volume_mesh(stl_path, target_element_size=mesh_size)
    bottom_nodes = get_bottom_nodes(nodes)
    top_nodes = get_internal_slave_nodes(nodes, elements, depth=search_depth)
    
    bottom_set = set(bottom_nodes)
    top_nodes = [n for n in top_nodes if n not in bottom_set]
    if len(top_nodes) == 0: raise ValueError("Внутренние узлы не найдены.")
    
    cx, cy = np.mean(nodes[top_nodes, 0]), np.mean(nodes[top_nodes, 1])
    z_top, z_bottom = np.max(nodes[:, 2]), np.min(nodes[:, 2])
    master_coords, force_vector = get_gost_load_vector(load_newtons, condition, z_top, z_bottom, cx, cy)

    cells = np.hstack((np.full((len(elements), 1), 4), elements)).astype(int).flatten()
    celltypes = np.full(len(elements), pv.CellType.TETRA)
    grid = pv.UnstructuredGrid(cells, celltypes, nodes)
    
    surf = grid.extract_surface(pass_pointid=True, algorithm='dataset_surface')
    surf_faces = surf.faces.reshape(-1, 4)[:, 1:] 
    original_ids = surf['vtkOriginalPointIds']
    surface_faces = original_ids[surf_faces].tolist()

    generate_inp(nodes, elements, bottom_nodes, top_nodes, force_vector, master_coords, material, job_name)
    run_ccx(job_name) 
    parsed_data = parse_dat(len(nodes), elements, job_name)
    return {
        "nodes": nodes.tolist(), 
        "displacements": parsed_data["displacements"], 
        "fem_values": parsed_data["stresses_vm"], # Отдаем фронтенду напряжения для раскраски
        "max_stress": parsed_data["max_stress"],
        "critical_node_idx": parsed_data["critical_node_idx"],
        "critical_stress_voigt": parsed_data["critical_stress_voigt"],
        "bottom_nodes": nodes[bottom_nodes].tolist(), 
        "top_nodes": nodes[top_nodes].tolist(),
        "master_coords": master_coords, 
        "force_vector": force_vector,
        "surface_faces": surface_faces,
        "stats": {"nodes_count": len(nodes), "elements_count": len(elements), "solve_time": round(time.time() - start_time, 2)}
    }
