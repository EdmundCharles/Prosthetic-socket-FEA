import os
import subprocess
import numpy as np
import pyvista as pv
import gmsh
import time
from scipy.spatial import cKDTree

# ==========================================
# БЛОК 1: ПОДГОТОВКА ГЕОМЕТРИИ
# ==========================================
def prepare_volume_mesh(stl_path, target_element_size=5.0):
    print("Оптимизация STL через PyVista...")
    mesh = pv.read(stl_path)
    if mesh.n_points > 50000:
        reduction_factor = 1.0 - (50000 / mesh.n_points)
        mesh = mesh.decimate(reduction_factor)
    
    clean_stl_path = "temp_clean.stl"
    mesh.save(clean_stl_path)

    print("Генерация объемной сетки через Gmsh...")
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0) 
    
    gmsh.merge(clean_stl_path)
    gmsh.model.geo.addSurfaceLoop([1], 1)
    gmsh.model.geo.addVolume([1], 1)
    gmsh.model.geo.synchronize()
    
    # ПРИМЕНЯЕМ РАЗМЕР СЕТКИ ИЗ ИНТЕРФЕЙСА
    gmsh.option.setNumber("Mesh.MeshSizeMin", target_element_size * 0.5)
    gmsh.option.setNumber("Mesh.MeshSizeMax", target_element_size)
    gmsh.model.mesh.generate(3)

    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes_raw = np.array(node_coords).reshape(-1, 3)
    tag_to_idx = {tag: idx for idx, tag in enumerate(node_tags)}

    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(dim=3)
    elements_raw = []
    
    for etype, enode_tags in zip(elem_types, elem_node_tags):
        if etype == 4: # Строго линейные C3D4
            nodes_per_elem = np.array(enode_tags).reshape(-1, 4)
            mapped = np.array([tag_to_idx.get(t, -1) for t in nodes_per_elem.flatten()]).reshape(-1, 4)
            valid_mask = (mapped != -1).all(axis=1)
            elements_raw.extend(mapped[valid_mask])

    gmsh.finalize()
    if os.path.exists(clean_stl_path): os.remove(clean_stl_path)

    elements_raw = np.array(elements_raw)
    if len(elements_raw) == 0:
        raise ValueError("Gmsh не смог создать сетку. Уменьшите размер КЭ.")

    used_nodes = np.unique(elements_raw)
    clean_nodes = nodes_raw[used_nodes]
    clean_nodes = np.nan_to_num(clean_nodes, nan=0.0)

    mapping = np.full(len(nodes_raw), -1, dtype=int)
    mapping[used_nodes] = np.arange(len(used_nodes))
    clean_elements = mapping[elements_raw]

    return clean_nodes, clean_elements

# ==========================================
# БЛОК 2: ПОИСК УЗЛОВ И ГОСТ
# ==========================================
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
    top_mask = surf_points[:, 2] >= (max_z - depth) # ПРИМЕНЯЕМ ГЛУБИНУ
    
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
    
    # Лимит для стабильности решателя
    if len(unique_slaves) > 300:
        step = len(unique_slaves) // 300
        unique_slaves = unique_slaves[::step]
        
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
# БЛОК 3: ИНТЕГРАЦИЯ CALCULIX
# ==========================================
def generate_inp(nodes, elements, bottom_nodes, top_nodes, force_vector, master_coords, material_type="petg_ortho", job_name="job"):
    with open(f"{job_name}.inp", "w") as f:
        f.write("*HEADING\nFGF Socket FEA\n*NODE, NSET=Nall\n")
        for i, (x, y, z) in enumerate(nodes): f.write(f"{i+1}, {x:.4f}, {y:.4f}, {z:.4f}\n")
        
        master_id = len(nodes) + 1
        f.write(f"{master_id}, {master_coords[0]:.4f}, {master_coords[1]:.4f}, {master_coords[2]:.4f}\n")
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
            # 2200, 2200, 1500 (Ez ниже), vxy, vxz, vyz, Gxy, Gxz, Gyz
            f.write("2200.0, 2200.0, 1500.0, 0.38, 0.38, 0.38, 800.0, 550.0,\n550.0\n")
        else:
            f.write("*ELASTIC\n2100.0, 0.38\n")
            
        f.write("*SOLID SECTION, ELSET=Eall, MATERIAL=FGF_PETG\n")
        f.write(f"*RIGID BODY, NSET=TopNodes, REF NODE={master_id}\n")
        f.write("*STEP\n*STATIC\n*BOUNDARY\nBottomNodes, 1, 3, 0.0\n*CLOAD\n")
        f.write(f"{master_id}, 1, {force_vector[0]:.2f}\n{master_id}, 2, {force_vector[1]:.2f}\n{master_id}, 3, {force_vector[2]:.2f}\n") 
        f.write("*NODE PRINT, NSET=Nall\nU\n*END STEP\n")

def run_ccx(job_name="job"):
    my_env = os.environ.copy()
    my_env["OMP_NUM_THREADS"] = "6"
    process = subprocess.run(["ccx_2.23", "-i", job_name], env=my_env, capture_output=True, text=True)
    if process.returncode != 0 or not os.path.exists(f"{job_name}.dat"): return False
    return True

def parse_dat(num_nodes, job_name="job"):
    displacements = np.zeros((num_nodes, 3))
    with open(f"{job_name}.dat", 'r') as f: lines = f.readlines()
    start_idx = next((i for i, line in enumerate(lines) if "displacements" in line), -1) + 2
    for line in lines[start_idx:]:
        if not line.strip(): break
        parts = line.split()
        if len(parts) >= 4 and int(parts[0])-1 < num_nodes: 
            displacements[int(parts[0])-1] = [float(parts[1]), float(parts[2]), float(parts[3])]
    disp_mag = np.linalg.norm(displacements, axis=1)
    return displacements.tolist(), disp_mag.tolist(), float(np.max(disp_mag))

# ==========================================
# БЛОК 4: ОРКЕСТРАТОР
# ==========================================
def process_socket_analysis(stl_path, load_newtons, condition="II", mesh_size=5.0, search_depth=150.0, material="petg_ortho"):
    job_name, start_time = "socket_analysis", time.time()
    
    nodes, elements = prepare_volume_mesh(stl_path, target_element_size=mesh_size)
    bottom_nodes = get_bottom_nodes(nodes)
    top_nodes = get_internal_slave_nodes(nodes, elements, depth=search_depth)
    
    bottom_set = set(bottom_nodes)
    top_nodes = [n for n in top_nodes if n not in bottom_set]
    
    if len(top_nodes) == 0: raise ValueError("Внутренние узлы пересеклись с дном или не найдены.")
    
    cx, cy = np.mean(nodes[top_nodes, 0]), np.mean(nodes[top_nodes, 1])
    z_top, z_bottom = np.max(nodes[:, 2]), np.min(nodes[:, 2])
    master_coords, force_vector = get_gost_load_vector(load_newtons, condition, z_top, z_bottom, cx, cy)

    # Передаем материал в генератор
    generate_inp(nodes, elements, bottom_nodes, top_nodes, force_vector, master_coords, material, job_name)
    if not run_ccx(job_name): raise RuntimeError("Ошибка CalculiX. Проверьте лог сервера.")
        
    displacements, disp_mag, max_disp = parse_dat(len(nodes), job_name)
    
    return {
        "nodes": nodes.tolist(), "displacements": displacements, "fem_values": disp_mag, "max_stress": max_disp,
        "bottom_nodes": nodes[bottom_nodes].tolist(), "top_nodes": nodes[top_nodes].tolist(),
        "master_coords": master_coords, "force_vector": force_vector,
        "stats": {"nodes_count": len(nodes), "elements_count": len(elements), "solve_time": round(time.time() - start_time, 2)}
    }