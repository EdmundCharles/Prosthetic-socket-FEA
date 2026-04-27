import os
import subprocess
import numpy as np
import pyvista as pv
import gmsh
from scipy.spatial import cKDTree
import time

# ==========================================
# БЛОК 1: ПОДГОТОВКА ГЕОМЕТРИИ (PyVista + Gmsh)
# ==========================================

def prepare_volume_mesh(stl_path, target_element_size=5.0):
    print("🛠 Оптимизация STL через PyVista...")
    mesh = pv.read(stl_path)
    if mesh.n_points > 50000:
        reduction_factor = 1.0 - (50000 / mesh.n_points)
        mesh = mesh.decimate(reduction_factor)
    
    clean_stl_path = "temp_clean.stl"
    mesh.save(clean_stl_path)

    print("🕸 Генерация объемной сетки через Gmsh...")
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0) 
    
    gmsh.merge(clean_stl_path)
    gmsh.model.geo.addSurfaceLoop([1], 1)
    gmsh.model.geo.addVolume([1], 1)
    gmsh.model.geo.synchronize()
    
    gmsh.option.setNumber("Mesh.MeshSizeMin", target_element_size * 0.5)
    gmsh.option.setNumber("Mesh.MeshSizeMax", target_element_size)
    gmsh.model.mesh.generate(3)

    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes = np.array(node_coords).reshape(-1, 3)
    tag_to_idx = {tag: idx for idx, tag in enumerate(node_tags)}

    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(dim=3)
    elements = []
    for etype, enode_tags in zip(elem_types, elem_node_tags):
        if etype == 4: 
            nodes_per_elem = np.array(enode_tags).reshape(-1, 4)
            mapped_elems = np.vectorize(tag_to_idx.get)(nodes_per_elem)
            elements.extend(mapped_elems)

    gmsh.finalize()
    if os.path.exists(clean_stl_path):
        os.remove(clean_stl_path)

    return nodes, np.array(elements)

# ==========================================
# БЛОК 2: ПОИСК УЗЛОВ И ГОСТ
# ==========================================

def get_bottom_nodes(nodes, tolerance=5.0):
    min_z = np.min(nodes[:, 2])
    bottom_indices = np.where(nodes[:, 2] <= min_z + tolerance)[0]
    return bottom_indices.tolist()

def get_internal_slave_nodes(nodes, elements, depth=150.0):
    print(f"🔍 Поиск внутренних slave-узлов на глубину {depth} мм...")
    
    cells = np.hstack((np.full((len(elements), 1), 4), elements)).astype(int).flatten()
    celltypes = np.full(len(elements), pv.CellType.TETRA)
    grid = pv.UnstructuredGrid(cells, celltypes, nodes)
    
    surf = grid.extract_surface()
    surf = surf.compute_normals(cell_normals=False, point_normals=True, auto_orient_normals=True)
    
    surf_points = surf.points
    surf_normals = surf['Normals']
    
    max_z = np.max(nodes[:, 2])
    target_z_min = max_z - depth
    top_mask = surf_points[:, 2] >= target_z_min
    
    if not np.any(top_mask):
        return []
    
    cx = np.mean(surf_points[top_mask, 0])
    cy = np.mean(surf_points[top_mask, 1])
    
    internal_coords = []
    for i in range(len(surf_points)):
        if not top_mask[i]: continue
            
        p = surf_points[i]
        n = surf_normals[i]
        
        vec_to_point = np.array([p[0] - cx, p[1] - cy, 0.0])
        norm_vec = np.linalg.norm(vec_to_point)
        if norm_vec < 1e-5: continue
        vec_to_point = vec_to_point / norm_vec
        
        n_xy = np.array([n[0], n[1], 0.0])
        norm_n = np.linalg.norm(n_xy)
        if norm_n > 1e-5:
            n_xy = n_xy / norm_n
            if np.dot(vec_to_point, n_xy) < -0.05:
                internal_coords.append(p)

    if len(internal_coords) == 0: return []
        
    tree = cKDTree(nodes)
    _, slave_indices = tree.query(internal_coords)
    unique_slaves = list(set(slave_indices.tolist()))
    
    # Оптимизация для скорости
    if len(unique_slaves) > 300:
        step = len(unique_slaves) // 300
        unique_slaves = unique_slaves[::step]
        print(f"⚡ Оптимизация: для RBE2 оставлено {len(unique_slaves)} узлов.")
        
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
    
    master_coords = [pt_x, pt_y, z_top + 50.0] 
    force_vector = [fx, fy, fz]
    
    print(f"📐 Вектор ГОСТ: Fx={fx:.1f}, Fy={fy:.1f}, Fz={fz:.1f}")
    return master_coords, force_vector

# ==========================================
# БЛОК 3: ИНТЕГРАЦИЯ CALCULIX
# ==========================================

def generate_inp(nodes, elements, bottom_nodes, top_nodes, force_vector, master_coords, job_name="job"):
    with open(f"{job_name}.inp", "w") as f:
        f.write("*HEADING\nFGF Socket FEA via CalculiX (GOST 10328)\n")
        f.write("*NODE, NSET=Nall\n")
        for i, (x, y, z) in enumerate(nodes):
            f.write(f"{i+1}, {x}, {y}, {z}\n")

        master_id = len(nodes) + 1
        f.write(f"{master_id}, {master_coords[0]:.2f}, {master_coords[1]:.2f}, {master_coords[2]:.2f}\n")

        f.write("*ELEMENT, TYPE=C3D4, ELSET=Eall\n")
        for i, el in enumerate(elements):
            f.write(f"{i+1}, {el[0]+1}, {el[1]+1}, {el[2]+1}, {el[3]+1}\n")

        def write_nset(name, node_indices):
            f.write(f"*NSET, NSET={name}\n")
            for i in range(0, len(node_indices), 10):
                f.write(", ".join([str(n+1) for n in node_indices[i:i+10]]) + "\n")

        write_nset("BottomNodes", bottom_nodes)
        write_nset("TopNodes", top_nodes)

        f.write("*MATERIAL, NAME=FGF_PLASTIC\n*ELASTIC\n2100.0, 0.35\n")
        f.write("*SOLID SECTION, ELSET=Eall, MATERIAL=FGF_PLASTIC\n")
        f.write(f"*RIGID BODY, NSET=TopNodes, REF NODE={master_id}\n")
        f.write("*STEP\n*STATIC\n*BOUNDARY\nBottomNodes, 1, 3, 0.0\n")
        
        f.write("*CLOAD\n")
        f.write(f"{master_id}, 1, {force_vector[0]:.2f}\n") 
        f.write(f"{master_id}, 2, {force_vector[1]:.2f}\n") 
        f.write(f"{master_id}, 3, {force_vector[2]:.2f}\n") 
        
        f.write("*NODE PRINT, NSET=Nall\nU\n*END STEP\n")

def run_ccx(job_name="job"):
    cmd = ["ccx_2.23", "-i", job_name]
    print(f"🚀 Запуск CalculiX: {' '.join(cmd)}")
    
    # Включаем многопоточность для ускорения!
    my_env = os.environ.copy()
    my_env["OMP_NUM_THREADS"] = "6"
    
    process = subprocess.run(cmd, env=my_env, capture_output=True, text=True)
    
    if process.returncode != 0 or not os.path.exists(f"{job_name}.dat"):
        print("❌ Ошибка CalculiX!")
        error_msg = process.stderr if process.stderr.strip() else process.stdout
        print("\n".join(error_msg.split('\n')[-15:]))
        return False
    return True

def parse_dat(num_nodes, job_name="job"):
    filename = f"{job_name}.dat"
    displacements = np.zeros((num_nodes, 3))

    if not os.path.exists(filename):
        raise FileNotFoundError(f"Файл {filename} не найден!")

    with open(filename, 'r') as f:
        lines = f.readlines()

    start_idx = -1
    for i, line in enumerate(lines):
        if "displacements (vx,vy,vz)" in line:
            start_idx = i + 2
            break

    if start_idx == -1:
         raise ValueError("Блок перемещений не найден в результатах!")

    for line in lines[start_idx:]:
        if line.strip() == "": break
        parts = line.split()
        if len(parts) >= 4:
            node_id = int(parts[0]) - 1
            if node_id < num_nodes: 
                displacements[node_id] = [float(parts[1]), float(parts[2]), float(parts[3])]

    disp_mag = np.linalg.norm(displacements, axis=1)
    
    # ИСПРАВЛЕНО: Теперь возвращаем и векторы смещений, и магнитуду!
    return displacements.tolist(), disp_mag.tolist(), float(np.max(disp_mag))

# ==========================================
# БЛОК 4: ГЛАВНЫЙ ОРКЕСТРАТОР
# ==========================================

def process_socket_analysis(stl_path, load_newtons, condition="II"):
    job_name = "socket_analysis"
    start_time = time.time() # Фиксируем старт
    
    # 1. Мешинг
    nodes, elements = prepare_volume_mesh(stl_path)
    
    # 2. Поиск узлов
    bottom_nodes = get_bottom_nodes(nodes)
    raw_slave_nodes = get_internal_slave_nodes(nodes, elements, depth=150.0) # Здесь уже есть прореживание
    
    # Считаем геометрические параметры
    cx, cy = np.mean(nodes[raw_slave_nodes, 0]), np.mean(nodes[raw_slave_nodes, 1])
    z_top, z_bottom = np.max(nodes[:, 2]), np.min(nodes[:, 2])

    # ГОСТ Вектор
    master_coords, force_vector = get_gost_load_vector(load_newtons, condition, z_top, z_bottom, cx, cy)

    # 3. Расчет
    generate_inp(nodes, elements, bottom_nodes, raw_slave_nodes, force_vector, master_coords, job_name)
    success = run_ccx(job_name)
    
    if not success:
        raise RuntimeError("CalculiX error")
        
    displacements, disp_mag, max_disp = parse_dat(len(nodes), job_name)
    
    total_time = round(time.time() - start_time, 2) # Считаем итог

    return {
        "nodes": nodes.tolist(),
        "displacements": displacements,
        "fem_values": disp_mag,
        "max_stress": max_disp,
        "bottom_nodes": nodes[bottom_nodes].tolist(),
        "top_nodes": nodes[raw_slave_nodes].tolist(),
        "master_coords": master_coords,
        "force_vector": force_vector,
        # НОВАЯ СТАТИСТИКА:
        "stats": {
            "nodes_count": len(nodes),
            "elements_count": len(elements),
            "slave_nodes_count": len(raw_slave_nodes),
            "solve_time": total_time,
            "element_type": "C3D4 (Linear Tet)",
            "solver": "CalculiX 2.23 (ccx_2.23)"
        }
    }