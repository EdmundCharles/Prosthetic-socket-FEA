import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

let chart = null;

// ==========================================
// 1. БИОМЕХАНИКА (CHART.JS)
// ==========================================
window.runBioAnalysis = async () => {
    const btn = event.target; 
    const originalText = btn.textContent;
    btn.textContent = "Считаем..."; 
    btn.disabled = true;

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                weight: parseFloat(document.getElementById('weight').value) || 80, 
                thigh_girth: 55, 
                movement_type: document.getElementById('moveType').value 
            })
        });
        
        if (!res.ok) throw new Error(`Ошибка сервера: ${await res.text()}`);
        const result = await res.json();
        
        document.getElementById('loadInput').value = Math.round(result.max_load);
        const recsHtml = result.recommendations.map(r => `<li style="margin-bottom: 5px;">${r}</li>`).join('');
        
        document.getElementById('resSummary').classList.remove('hidden');
        document.getElementById('resText').innerHTML = `
            <b>Пиковая нагрузка:</b> ${Math.round(result.max_load)} Н<br>
            <b>Срок службы:</b> ${result.service_life} лет<br>
            <ul style="padding-left: 15px; margin-top: 8px; font-size: 12px;">${recsHtml}</ul>
        `;

        if (chart) chart.destroy();
        chart = new Chart(document.getElementById('loadChart'), {
            type: 'line',
            data: { 
                labels: result.time_data.map(t => t.toFixed(2)), 
                datasets: [{ 
                    label: 'Нагрузка (Н)', 
                    data: result.load_data, 
                    borderColor: '#15803d', 
                    backgroundColor: 'rgba(21,128,61,0.1)', 
                    fill: true 
                }] 
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    } catch (e) { 
        alert("Ошибка биомеханики: " + e.message); 
    } finally { 
        btn.textContent = originalText;
        btn.disabled = false; 
    }
};

// ==========================================
// 2. ИНИЦИАЛИЗАЦИЯ 3D СЦЕНЫ (THREE.JS)
// ==========================================
const container = document.getElementById('viewer3d');
const scene = new THREE.Scene(); 
scene.background = new THREE.Color(0xf3f4f6);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000); 
camera.position.set(300, 200, 300);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8); 
dirLight.position.set(200, 500, 200); 
scene.add(dirLight);

const grid = new THREE.GridHelper(400, 40, 0xcccccc, 0xdddddd);
scene.add(grid);

// --- ВОЗВРАЩАЕМ ЦИФРЫ НА СЕТКЕ КООРДИНАТ ---
function createTextSprite(text) {
    const canvas = document.createElement('canvas');
    canvas.width = 128; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'transparent'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = 'bold 20px Arial'; ctx.fillStyle = '#6b7280'; 
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
    sprite.scale.set(30, 15, 1);
    return sprite;
}

for (let i = -200; i <= 200; i += 50) {
    if (i === 0) continue;
    let spriteX = createTextSprite(i + ' мм'); spriteX.position.set(i, 0, 20); scene.add(spriteX);
    let spriteZ = createTextSprite(i + ' мм'); spriteZ.position.set(20, 0, i); scene.add(spriteZ);
}
// ------------------------------------------

const modelGroup = new THREE.Group(); 
modelGroup.rotation.x = -Math.PI / 2; 
scene.add(modelGroup);

let currentMesh = null;
let ghostMesh = null;
let helpersGroup = new THREE.Group();
modelGroup.add(helpersGroup);

let vertexMap = [];
let geometryOffsets = {x: 0, y: 0, z: 0};

const resize = () => {
    if (container.clientWidth === 0) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
};
window.addEventListener('resize', resize);
new ResizeObserver(resize).observe(container);

// ==========================================
// 3. ЛОГИКА ДЕФОРМАЦИИ И ФАЙЛОВ
// ==========================================
const applyDeformation = (scale) => {
    if (!currentMesh || !vertexMap.length) return;
    const pos = currentMesh.geometry.attributes.position;
    const orig = currentMesh.geometry.attributes.originalPosition;
    for (let i = 0; i < orig.count; i++) {
        pos.setXYZ(i, orig.getX(i) + vertexMap[i].dx * scale, orig.getY(i) + vertexMap[i].dy * scale, orig.getZ(i) + vertexMap[i].dz * scale);
    }
    pos.needsUpdate = true;
};

document.getElementById('dispScale').addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    document.getElementById('scaleVal').textContent = val.toFixed(1);
    applyDeformation(val);
});

document.getElementById('showGhost').addEventListener('change', (e) => {
    if (ghostMesh) ghostMesh.visible = e.target.checked;
});

document.getElementById('stlInput').addEventListener('change', (e) => {
    const file = e.target.files[0]; 
    if (!file) return;
    
    document.getElementById('topStatus').textContent = "Чтение файла...";
    
    const reader = new FileReader();
    reader.onload = (event) => {
        if (currentMesh) modelGroup.remove(currentMesh);
        if (ghostMesh) modelGroup.remove(ghostMesh);
        helpersGroup.clear();
        vertexMap = [];

        const geometry = new STLLoader().parse(event.target.result);
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        
        geometryOffsets = { x: -(box.max.x + box.min.x)/2, y: -(box.max.y + box.min.y)/2, z: -box.min.z };
        geometry.translate(geometryOffsets.x, geometryOffsets.y, geometryOffsets.z);
        geometry.computeVertexNormals();
        geometry.setAttribute('originalPosition', geometry.attributes.position.clone());
        
        currentMesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xe5e7eb }));
        ghostMesh = new THREE.Mesh(geometry.clone(), new THREE.MeshStandardMaterial({ color: 0x9ca3af, transparent: true, opacity: 0.15, depthWrite: false }));
        ghostMesh.visible = document.getElementById('showGhost').checked;
        
        modelGroup.add(currentMesh, ghostMesh);
        
        controls.target.copy(new THREE.Vector3(0, 0, (box.max.z - box.min.z) / 2));
        
        document.getElementById('calcBtn').disabled = false;
        document.getElementById('topStatus').textContent = "Модель готова к расчету";
        resize();
    };
    reader.readAsArrayBuffer(file);
});

// ==========================================
// 4. ЗАПУСК МКЭ РАСЧЕТА
// ==========================================
document.getElementById('calcBtn').addEventListener('click', async () => {
    const fd = new FormData();
    fd.append('file', document.getElementById('stlInput').files[0]);
    fd.append('load_newtons', document.getElementById('loadInput').value);
    fd.append('condition', document.getElementById('gostCondition').value);
    fd.append('mesh_size', document.getElementById('meshSize').value);
    fd.append('search_depth', document.getElementById('searchDepth').value);
    fd.append('material', document.getElementById('matType').value);

    const btn = document.getElementById('calcBtn');
    const prog = document.getElementById('progressBar');
    
    btn.disabled = true;
    document.getElementById('progressContainer').classList.remove('hidden');
    prog.style.width = '15%';
    document.getElementById('topStatus').textContent = "Выполняется МКЭ анализ...";

    // Фейковая анимация прогресса для UX
    let progress = 15;
    const progressInterval = setInterval(() => {
        if (progress < 90) {
            progress += progress < 40 ? 5 : 2;
            prog.style.width = `${progress}%`;
        }
    }, 300);

    try {
        const res = await fetch('/api/calculate', { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        
        clearInterval(progressInterval);
        prog.style.width = '100%';
        setTimeout(() => document.getElementById('progressContainer').classList.add('hidden'), 1000);

        document.getElementById('topStatus').textContent = "Расчет успешно завершен";
        
        // --- ВОЗВРАЩАЕМ ПАНЕЛИ И СТАТИСТИКУ ---
        document.getElementById('legendOverlay').classList.remove('hidden');
        document.getElementById('resSummary').classList.remove('hidden');
        document.getElementById('techReport').classList.remove('hidden');
        
        document.getElementById('legendMax').textContent = data.max_stress.toFixed(2);
        document.getElementById('legendMid').textContent = (data.max_stress / 2).toFixed(2);

        document.getElementById('resText').innerHTML = `
            Максимальное смещение:<br>
            <span style="color: #dc2626; font-size: 16px; font-weight: bold;">${data.max_stress.toFixed(2)} мм</span>
        `;

        if (data.stats) {
            document.getElementById('statNodes').textContent = data.stats.nodes_count.toLocaleString();
            document.getElementById('statElems').textContent = data.stats.elements_count.toLocaleString();
            document.getElementById('statTime').textContent = data.stats.solve_time + " с";
        }
        // -------------------------------------

        const geom = currentMesh.geometry;
        const origPos = geom.attributes.originalPosition;
        const colors = new Float32Array(origPos.count * 3);
        vertexMap = new Array(origPos.count);

        for (let i = 0; i < origPos.count; i++) {
            const vx = origPos.getX(i) - geometryOffsets.x;
            const vy = origPos.getY(i) - geometryOffsets.y;
            const vz = origPos.getZ(i) - geometryOffsets.z;
            
            let minDistSq = Infinity, val = 0, dx = 0, dy = 0, dz = 0;
            
            for (let j = 0; j < data.fem_nodes.length; j += 5) {
                const d2 = (vx-data.fem_nodes[j][0])**2 + (vy-data.fem_nodes[j][1])**2 + (vz-data.fem_nodes[j][2])**2;
                if (d2 < minDistSq) { 
                    minDistSq = d2; 
                    val = data.fem_values[j]; 
                    dx = data.displacements[j][0]; dy = data.displacements[j][1]; dz = data.displacements[j][2]; 
                }
            }
            vertexMap[i] = {dx, dy, dz};
            const c = new THREE.Color().setHSL((1 - Math.min(val/data.max_stress, 1))*0.66, 1, 0.5);
            colors[i*3] = c.r; colors[i*3+1] = c.g; colors[i*3+2] = c.b;
        }
        
        geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        currentMesh.material.vertexColors = true; 
        currentMesh.material.color.setHex(0xffffff); 
        currentMesh.material.needsUpdate = true;
        
        applyDeformation(parseFloat(document.getElementById('dispScale').value));

        // --- ВОЗВРАЩАЕМ ОТРИСОВКУ ВЕКТОРОВ И СВЯЗЕЙ ---
        helpersGroup.clear();
        
        if (data.bottom_coords && data.bottom_coords.length > 0) {
            const markerMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial({ color: 0xff0000 }), data.bottom_coords.length);
            const dummy = new THREE.Object3D();
            for (let i = 0; i < data.bottom_coords.length; i++) {
                dummy.position.set(data.bottom_coords[i][0] + geometryOffsets.x, data.bottom_coords[i][1] + geometryOffsets.y, data.bottom_coords[i][2] + geometryOffsets.z);
                dummy.updateMatrix(); markerMesh.setMatrixAt(i, dummy.matrix);
            }
            markerMesh.instanceMatrix.needsUpdate = true; helpersGroup.add(markerMesh);
        }

        if (data.top_coords && data.top_coords.length > 0 && data.master_coords) {
            const slaveMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(1.0, 8, 8), new THREE.MeshBasicMaterial({ color: 0x00ffff, transparent: true, opacity: 0.6 }), data.top_coords.length);
            const dummy = new THREE.Object3D();
            for (let i = 0; i < data.top_coords.length; i++) {
                dummy.position.set(data.top_coords[i][0] + geometryOffsets.x, data.top_coords[i][1] + geometryOffsets.y, data.top_coords[i][2] + geometryOffsets.z);
                dummy.updateMatrix(); slaveMesh.setMatrixAt(i, dummy.matrix);
            }
            slaveMesh.instanceMatrix.needsUpdate = true; helpersGroup.add(slaveMesh); 

            const masterPos = new THREE.Vector3(data.master_coords[0] + geometryOffsets.x, data.master_coords[1] + geometryOffsets.y, data.master_coords[2] + geometryOffsets.z);
            const lineMat = new THREE.LineBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.15 }); 
            
            data.top_coords.forEach((p, idx) => {
                if (idx % 15 !== 0) return;
                const pLocal = new THREE.Vector3(p[0] + geometryOffsets.x, p[1] + geometryOffsets.y, p[2] + geometryOffsets.z);
                helpersGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([masterPos, pLocal]), lineMat));
            });

            if (data.force_vector) {
                const dir = new THREE.Vector3(data.force_vector[0], data.force_vector[1], data.force_vector[2]).normalize(); 
                helpersGroup.add(new THREE.ArrowHelper(dir, masterPos, 70, 0xdc2626, 15, 8));
            }
        }
        // ----------------------------------------------

    } catch (e) { 
        clearInterval(progressInterval);
        document.getElementById('progressContainer').classList.add('hidden');
        document.getElementById('topStatus').textContent = "Ошибка при расчете";
        alert("Сбой МКЭ: " + e.message); 
    } finally { 
        btn.disabled = false; 
    }
});

const animate = () => { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); };
animate();