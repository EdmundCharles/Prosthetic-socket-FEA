import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

// ==========================================
// ЧАСТЬ 1: БИОМЕХАНИКА И ГРАФИКИ (CHART.JS)
// ==========================================

// Хранилище для экземпляров Chart.js
const bioCharts = { fz: null, fy: null, fx: null };

// Функция для показа/скрытия доп. полей
window.toggleJumpInput = () => {
    const isJump = document.getElementById('moveType').value === 'jump';
    document.getElementById('jumpParams').classList.toggle('hidden', !isJump);
};

window.runBioAnalysis = async () => {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "Расчет...";
    btn.disabled = true;

    try {
        // Собираем все новые данные
        const payload = {
            weight: parseFloat(document.getElementById('weight').value),
            height: parseFloat(document.getElementById('height').value),
            thigh_girth: parseFloat(document.getElementById('thighGirth').value),
            steps_per_day: parseInt(document.getElementById('stepsDay').value),
            movement_type: document.getElementById('moveType').value,
            jump_height: parseFloat(document.getElementById('jumpHeight').value) || null,
            socket: {
                material: "carbon_fiber", // Можно добавить выбор в HTML позже
                critical_load: 3000
            }
        };

        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });  

        if (!res.ok) throw new Error(await res.text());
        const result = await res.json();

        // 1. Обновляем текстовые показатели
        document.getElementById('bioStats').classList.remove('hidden');
        document.getElementById('statMaxLoad').textContent = Math.round(result.max_load);
        document.getElementById('statRisk').textContent = Math.round(result.risk_percentage);
        document.getElementById('statLife').textContent = result.service_life;

        // 2. Обновляем поле нагрузки для МКЭ (автоматический перенос данных)
        document.getElementById('loadInput').value = Math.round(result.max_load);

        // 3. Выводим рекомендации
        const recsHtml = result.recommendations.map(r => `<li>${r}</li>`).join('');
        document.getElementById('resTextBio').innerHTML = `<ul style="padding-left: 20px;">${recsHtml}</ul>`;

        // 4. Вызываем функцию отрисовки 3-х графиков
        updateChart(result.time_data, result.fz_data, result.fy_data, result.fx_data);

    } catch (e) { 
        alert("Ошибка биомеханики: " + e.message); 
    } finally { 
        btn.textContent = originalText;
        btn.disabled = false; 
    }
};


function updateChart(timeData, fz, fy, fx) {
    const labels = timeData.map(t => t.toFixed(2));

    const chartConfigs = [
        { id: 'chartFz', data: fz, label: 'Fz (Вертикальная нагрузка), Н', color: '#15803d', bg: 'rgba(21,128,61,0.05)' },
        { id: 'chartFy', data: fy, label: 'Fy (Продольная сила), Н', color: '#0ea5e9', bg: 'rgba(14,165,233,0.05)' },
        { id: 'chartFx', data: fx, label: 'Fx (Боковая сила), Н', color: '#f97316', bg: 'rgba(249,115,22,0.05)' }
    ];

    chartConfigs.forEach(config => {
        const ctx = document.getElementById(config.id).getContext('2d');
        const key = config.id.replace('chart', '').toLowerCase();

        if (bioCharts[key]) bioCharts[key].destroy();

        bioCharts[key] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: config.label,
                    data: config.data,
                    borderColor: config.color,
                    backgroundColor: config.bg,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0, // Убираем точки для чистоты линии
                    pointHoverRadius: 6,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { 
                    legend: { position: 'top', align: 'end', labels: { boxWidth: 12, usePointStyle: true } } 
                },
                scales: {
                    x: { grid: { color: '#f1f5f9' }, ticks: { maxTicksLimit: 10 } },
                    y: { grid: { color: '#f1f5f9' } }
                }
            }
        });
    });
}

// ==========================================
// 2. ИНИЦИАЛИЗАЦИЯ 3D СЦЕНЫ (THREE.JS)
// ==========================================
const container = document.getElementById('viewer3d');
const scene = new THREE.Scene(); 
scene.background = new THREE.Color(0xffffff); 

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

const grid = new THREE.GridHelper(400, 40, 0xcccccc, 0xe5e7eb);
scene.add(grid);

function createTextSprite(text) {
    const canvas = document.createElement('canvas');
    canvas.width = 128; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'transparent'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = 'bold 20px -apple-system, sans-serif'; ctx.fillStyle = '#6b7280'; 
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

const modelGroup = new THREE.Group(); 
modelGroup.rotation.x = -Math.PI / 2; 
scene.add(modelGroup);

// Глобальный флаг для отслеживания наличия результатов МКЭ
window.femResultsAvailable = false;

let currentMesh = null;
let ghostMesh = null;
let wireframeMesh = null;
let helpersGroup = new THREE.Group();
let kinematicGroup = new THREE.Group(); // Группа только для связей и узлов
modelGroup.add(helpersGroup);

let vertexMap = [];
let geometryOffsets = {x: 0, y: 0, z: 0};

function disposeHierarchy(obj) {
    if (!obj) return;
    if (obj.children && obj.children.length > 0) {
        for (let i = obj.children.length - 1; i >= 0; i--) {
            const child = obj.children[i];
            disposeHierarchy(child);
            obj.remove(child);
        }
    }
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
        if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
        else obj.material.dispose();
    }
}

const resize = () => {
    if (container.clientWidth === 0) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
};
window.addEventListener('resize', resize);
new ResizeObserver(resize).observe(container);

const applyDeformation = (scale) => {
    if (!currentMesh || !vertexMap.length) return;
    const pos = currentMesh.geometry.attributes.position;
    const orig = currentMesh.geometry.attributes.originalPosition;
    for (let i = 0; i < orig.count; i++) {
        pos.setXYZ(
            i, 
            orig.getX(i) + vertexMap[i].dx * scale, 
            orig.getY(i) + vertexMap[i].dy * scale, 
            orig.getZ(i) + vertexMap[i].dz * scale
        );
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

document.getElementById('showWireframe').addEventListener('change', (e) => {
    if (wireframeMesh) wireframeMesh.visible = e.target.checked;
});

// НОВЫЙ СЛУШАТЕЛЬ ДЛЯ КИНЕМАТИКИ
document.getElementById('showKinematics').addEventListener('change', (e) => {
    if (kinematicGroup) kinematicGroup.visible = e.target.checked;
});

// Загрузка STL
document.getElementById('stlInput').addEventListener('change', (e) => {
    const file = e.target.files[0]; 
    if (!file) return;

     // Сбрасываем флаг и скрываем старые результаты МКЭ
    window.femResultsAvailable = false;
    document.getElementById('resSummary')?.classList.add('hidden');
    document.getElementById('techReport')?.classList.add('hidden');
    document.getElementById('legendOverlay')?.classList.add('hidden');
    
    document.getElementById('topStatus').textContent = "Чтение файла...";
    
    const reader = new FileReader();
    reader.onload = (event) => {
        if (currentMesh) { disposeHierarchy(currentMesh); modelGroup.remove(currentMesh); }
        if (ghostMesh) { disposeHierarchy(ghostMesh); modelGroup.remove(ghostMesh); }
        disposeHierarchy(helpersGroup);
        vertexMap = [];

        const geometry = new STLLoader().parse(event.target.result);
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        
        geometryOffsets = { x: -(box.max.x + box.min.x)/2, y: -(box.max.y + box.min.y)/2, z: -box.min.z };
        geometry.translate(geometryOffsets.x, geometryOffsets.y, geometryOffsets.z);
        geometry.computeVertexNormals();
        geometry.setAttribute('originalPosition', geometry.attributes.position.clone());
        
        currentMesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.3 }));
        
        wireframeMesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0x0f172a, wireframe: true, transparent: true, opacity: 0.1, depthWrite: false }));
        wireframeMesh.visible = document.getElementById('showWireframe').checked;
        currentMesh.add(wireframeMesh);
        
        ghostMesh = new THREE.Mesh(geometry.clone(), new THREE.MeshStandardMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.15, depthWrite: false }));
        ghostMesh.visible = document.getElementById('showGhost').checked;
        
        modelGroup.add(currentMesh, ghostMesh);
        controls.target.copy(new THREE.Vector3(0, 0, (box.max.z - box.min.z) / 2));
        
        document.getElementById('calcBtn').disabled = false;
        document.getElementById('topStatus').textContent = "Модель загружена";
        resize();
    };
    reader.readAsArrayBuffer(file);
});

// ЗАПУСК МКЭ РАСЧЕТА
document.getElementById('calcBtn').addEventListener('click', async () => {
    const fd = new FormData();
    fd.append('file', document.getElementById('stlInput').files[0]);
    fd.append('load_newtons', document.getElementById('loadInput').value);
    fd.append('condition', document.getElementById('gostCondition').value);
    fd.append('mesh_size', document.getElementById('meshSize').value);
    fd.append('search_depth', document.getElementById('searchDepth').value);
    fd.append('material', document.getElementById('matType').value);

    const btn = document.getElementById('calcBtn');
    
    btn.disabled = true;
    document.getElementById('progressContainer').classList.remove('hidden');
    document.getElementById('topStatus').textContent = "Выполняется МКЭ анализ...";

    const startTime = Date.now();
    const estimatedTimeMs = 45000; 
    
    const progressInterval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        let newProgress = (elapsed / estimatedTimeMs) * 90; 
        if (newProgress > 95) newProgress = 95; 
        
        document.getElementById('progressBar').style.width = `${newProgress}%`;
        document.getElementById('progressPercent').textContent = `${Math.floor(newProgress)}%`;
        
        const progText = document.getElementById('progressText');
        if (newProgress < 15) progText.textContent = "Подготовка геометрии...";
        else if (newProgress < 30) progText.textContent = "Построение адаптивной сетки Gmsh...";
        else if (newProgress < 50) progText.textContent = "Построение матриц жесткости...";
        else if (newProgress < 85) progText.textContent = "Решение СЛАУ (CalculiX)...";
        else progText.textContent = "Извлечение результатов...";
    }, 500);

    try {
        const res = await fetch('/api/calculate', { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();

        // Устанавливаем флаг, что результаты получены
        window.femResultsAvailable = true;
        
        clearInterval(progressInterval);
        document.getElementById('progressBar').style.width = '100%';
        document.getElementById('progressPercent').textContent = '100%';
        document.getElementById('progressText').textContent = "Визуализация...";
        setTimeout(() => document.getElementById('progressContainer').classList.add('hidden'), 800);

        document.getElementById('topStatus').textContent = "Расчет завершен";
        
        document.getElementById('legendOverlay').classList.remove('hidden');
        document.getElementById('resSummary').classList.remove('hidden');
        document.getElementById('techReport').classList.remove('hidden');
        
        document.getElementById('legendMax').textContent = data.max_stress.toFixed(2);
        document.getElementById('legendMid').textContent = (data.max_stress / 2).toFixed(2);

        document.getElementById('resText').innerHTML = `
            <div style="font-size: 15px; margin-bottom: 8px; color: var(--text-main);">Максимальное смещение:</div>
            <div style="color: #dc2626; font-size: 24px; font-weight: 700; letter-spacing: -0.02em;">${data.max_stress.toFixed(2)} мм</div>
        `;

        if (data.stats) {
            document.getElementById('statNodes').textContent = data.stats.nodes_count.toLocaleString();
            document.getElementById('statElems').textContent = data.stats.elements_count.toLocaleString();
            document.getElementById('statTime').textContent = data.stats.solve_time + " с";
        }

        const femGeom = new THREE.BufferGeometry();
        const vertices = new Float32Array(data.fem_nodes.length * 3);
        const colors = new Float32Array(data.fem_nodes.length * 3);
        vertexMap = new Array(data.fem_nodes.length);

        data.fem_nodes.forEach((node, i) => {
            vertices[i * 3]     = node[0] + geometryOffsets.x;
            vertices[i * 3 + 1] = node[1] + geometryOffsets.y;
            vertices[i * 3 + 2] = node[2] + geometryOffsets.z;

            vertexMap[i] = { dx: data.displacements[i][0], dy: data.displacements[i][1], dz: data.displacements[i][2] };

            const val = data.fem_values[i];
            const c = new THREE.Color().setHSL((1 - Math.min(val / data.max_stress, 1)) * 0.66, 1, 0.5);
            colors[i * 3] = c.r; colors[i * 3 + 1] = c.g; colors[i * 3 + 2] = c.b;
        });

        femGeom.setAttribute('originalPosition', new THREE.BufferAttribute(new Float32Array(vertices), 3));
        femGeom.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
        femGeom.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const indices = [];
        if (data.surface_faces) { data.surface_faces.forEach(face => { indices.push(face[0], face[1], face[2]); }); }
        femGeom.setIndex(indices);
        femGeom.computeVertexNormals();

        if (currentMesh) {
            currentMesh.geometry.dispose();
            currentMesh.geometry = femGeom;
            currentMesh.material.vertexColors = true;
            currentMesh.material.color.setHex(0xffffff);
            currentMesh.material.needsUpdate = true;
        }

        if (wireframeMesh) {
            wireframeMesh.geometry.dispose();
            wireframeMesh.geometry = femGeom; 
        }
        
        applyDeformation(parseFloat(document.getElementById('dispScale').value));
        
        // --- ПЕРЕРАСПРЕДЕЛЕНИЕ ГРУПП ---
        disposeHierarchy(helpersGroup);
        helpersGroup.clear();
        
        kinematicGroup = new THREE.Group();
        kinematicGroup.visible = document.getElementById('showKinematics').checked;
        helpersGroup.add(kinematicGroup);

        if (data.bottom_coords && data.bottom_coords.length > 0) {
            const markerMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial({ color: 0xdc2626 }), data.bottom_coords.length);
            const dummy = new THREE.Object3D();
            for (let i = 0; i < data.bottom_coords.length; i++) {
                dummy.position.set(data.bottom_coords[i][0] + geometryOffsets.x, data.bottom_coords[i][1] + geometryOffsets.y, data.bottom_coords[i][2] + geometryOffsets.z);
                dummy.updateMatrix(); markerMesh.setMatrixAt(i, dummy.matrix);
            }
            markerMesh.instanceMatrix.needsUpdate = true; 
            helpersGroup.add(markerMesh); // Заделка видна всегда
        }

        if (data.top_coords && data.top_coords.length > 0 && data.master_coords) {
            const slaveMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(1.0, 8, 8), new THREE.MeshBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.6 }), data.top_coords.length);
            const dummy = new THREE.Object3D();
            for (let i = 0; i < data.top_coords.length; i++) {
                dummy.position.set(data.top_coords[i][0] + geometryOffsets.x, data.top_coords[i][1] + geometryOffsets.y, data.top_coords[i][2] + geometryOffsets.z);
                dummy.updateMatrix(); slaveMesh.setMatrixAt(i, dummy.matrix);
            }
            slaveMesh.instanceMatrix.needsUpdate = true; 
            kinematicGroup.add(slaveMesh); // Узлы в отключаемую группу

            const masterPos = new THREE.Vector3(data.master_coords[0] + geometryOffsets.x, data.master_coords[1] + geometryOffsets.y, data.master_coords[2] + geometryOffsets.z);
            const lineMat = new THREE.LineBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.15 }); 
            
            data.top_coords.forEach((p, idx) => {
                if (idx % 15 !== 0) return;
                const pLocal = new THREE.Vector3(p[0] + geometryOffsets.x, p[1] + geometryOffsets.y, p[2] + geometryOffsets.z);
                kinematicGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([masterPos, pLocal]), lineMat)); // Паутина в отключаемую группу
            });

            if (data.force_vector) {
                const dir = new THREE.Vector3(data.force_vector[0], data.force_vector[1], data.force_vector[2]).normalize(); 
                helpersGroup.add(new THREE.ArrowHelper(dir, masterPos, 70, 0xdc2626, 15, 8)); // Красная стрелка остается в главной группе!
            }
        }

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