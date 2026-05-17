import os
import subprocess
import numpy as np
import pyvista as pv
import gmsh
import math
import time
from scipy.spatial import cKDTree

# ==========================================
# БЛОК 1: ПОДГОТОВКА ГЕОМЕТРИИ (АДАПТИВНАЯ СЕТКА)
# ==========================================
def prepare_volume_mesh(stl_path, target_element_size=5.0):
    print("Оптимизация STL через PyVista...")
    mesh = pv.read(stl_path)
    
    # 1. Базовая сшивка
    mesh = mesh.clean()
    
    # 2. Аккуратное сжатие (только для сверхтяжелых файлов)
    # Используем decimate_pro с preserve_topology=True, чтобы не порвать верхний край гильзы!
    if mesh.n_points > 100000:
        reduction_factor = 1.0 - (100000 / mesh.n_points)
        mesh = mesh.decimate_pro(reduction_factor, preserve_topology=True)
        mesh = mesh.clean()
    
    clean_stl_path = "temp_clean.stl"
    mesh.save(clean_stl_path)

    print("Генерация CAD-геометрии и объемной сетки через Gmsh...")
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0) 
    
    gmsh.merge(clean_stl_path)
    
    # 3. Восстановление B-Rep (CAD)
    gmsh.model.mesh.classifySurfaces(40 * math.pi / 180, True, True, math.pi)
    gmsh.model.mesh.createGeometry()
    gmsh.model.geo.synchronize()
    
    s_entities = gmsh.model.getEntities(2)
    s_tags = [tag for dim, tag in s_entities]
    
    sl = gmsh.model.geo.addSurfaceLoop(s_tags)
    gmsh.model.geo.addVolume([sl])
    gmsh.model.geo.synchronize()

    # ==============================================================
    # 4. МАГИЯ: АДАПТАЦИЯ ПО КРИВИЗНЕ (ЛЕЧИМ "ГОРЫ" НА КРОМКАХ)
    # ==============================================================
    # Разрешаем генератору уменьшать элементы вплоть до 0.5 мм на острых углах и кромках
    gmsh.option.setNumber("Mesh.MeshSizeMin", 1) 
    # На ровных стенках используем крупный шаг (заданный пользователем)
    gmsh.option.setNumber("Mesh.MeshSizeMax", target_element_size)
    
    # Включаем алгоритм вычисления размера элемента на основе кривизны поверхности
    gmsh.option.setNumber("Mesh.CharacteristicLengthFromCurvature", 1)
    # Указываем, что на 360 градусов изгиба должно приходиться как минимум 20 элементов
    # Это заставит Gmsh плотно "облепить" тонкий край гильзы мелкими треугольниками
    gmsh.option.setNumber("Mesh.MinimumElementsPerTwoPi", 10)

    # Оптимизация формы (чтобы не было вырожденных тетраэдров)
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
    if len(elements_raw) == 0:
        raise ValueError("Gmsh не смог создать сетку. Убедитесь, что модель замкнута.")

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
    
    # Собираем ВСЕ внутренние узлы (лимит убран для CLOAD)
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
# БЛОК 3: ИНТЕГРАЦИЯ CALCULIX (CLOAD)
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
        
        # Распределяем силу по всем внутренним узлам
        f.write("*CLOAD\n")
        num_slaves = len(top_nodes)
        if num_slaves > 0:
            fx_i = force_vector[0] / num_slaves
            fy_i = force_vector[1] / num_slaves
            fz_i = force_vector[2] / num_slaves
            for n in top_nodes:
                if abs(fx_i) > 1e-5: f.write(f"{n+1}, 1, {fx_i:.5f}\n")
                if abs(fy_i) > 1e-5: f.write(f"{n+1}, 2, {fy_i:.5f}\n")
                if abs(fz_i) > 1e-5: f.write(f"{n+1}, 3, {fz_i:.5f}\n")
        
        f.write("*NODE PRINT, NSET=Nall\nU\n*END STEP\n")

def run_ccx(job_name="job"):
    my_env = os.environ.copy()
    my_env["OMP_NUM_THREADS"] = "6"
    # Путь к исполняющему файлу CalculiX
    ccx_path = r"c:\Calculix\bin\ccx_2.23.exe"
    process = subprocess.run([ccx_path, "-i", job_name], env=my_env, capture_output=True, text=True)
    
    if process.returncode != 0 or not os.path.exists(f"{job_name}.dat"):
        log_output = process.stdout + "\n" + process.stderr
        if os.path.exists(f"{job_name}.out"):
            with open(f"{job_name}.out", "r") as f:
                log_output += "\n" + f.read()[-1500:]
        
        error_msg = f"КРИТИЧЕСКИЙ СБОЙ CalculiX (Код {process.returncode})\nПодробности лога:\n{log_output[-800:]}"
        raise RuntimeError(error_msg)
        
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

    cells = np.hstack((np.full((len(elements), 1), 4), elements)).astype(int).flatten()
    celltypes = np.full(len(elements), pv.CellType.TETRA)
    grid = pv.UnstructuredGrid(cells, celltypes, nodes)
    
    # Извлечение топологии (убрал PyVistaFutureWarning)
    surf = grid.extract_surface(pass_pointid=True, algorithm='dataset_surface')
    surf_faces = surf.faces.reshape(-1, 4)[:, 1:] 
    
    original_ids = surf['vtkOriginalPointIds']
    surface_faces = original_ids[surf_faces].tolist()

    generate_inp(nodes, elements, bottom_nodes, top_nodes, force_vector, master_coords, material, job_name)
    run_ccx(job_name) 
        
    displacements, disp_mag, max_disp = parse_dat(len(nodes), job_name)
    
    return {
        "nodes": nodes.tolist(), 
        "displacements": displacements, 
        "fem_values": disp_mag, 
        "max_stress": max_disp,
        "bottom_nodes": nodes[bottom_nodes].tolist(), 
        "top_nodes": nodes[top_nodes].tolist(),
        "master_coords": master_coords, 
        "force_vector": force_vector,
        "surface_faces": surface_faces,
        "stats": {"nodes_count": len(nodes), "elements_count": len(elements), "solve_time": round(time.time() - start_time, 2)}
    }