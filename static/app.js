import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

// ==========================================
// ЧАСТЬ 1: БИОМЕХАНИКА И ГРАФИКИ (CHART.JS)
// ==========================================

let chart = null;

window.runBioAnalysis = async () => {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "Считаем...";
    btn.disabled = true;

    try {
        const data = {
            weight: parseFloat(document.getElementById('weight').value) || 80,
            thigh_girth: 55, 
            movement_type: document.getElementById('moveType').value
        };

        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (!res.ok) throw new Error(`Ошибка сервера: ${await res.text()}`);
        const result = await res.json();
        
        document.getElementById('loadInput').value = Math.round(result.max_load);
        
        const recsHtml = result.recommendations.map(r => `<li style="margin-bottom: 5px;">${r}</li>`).join('');
        const lifeColor = result.service_life < 2 ? 'red' : 'green';
        
        document.getElementById('resText').innerHTML = `
            <b>Срок службы:</b> <span style="color: ${lifeColor}">${result.service_life} лет</span><br>
            <b>Пиковая нагрузка:</b> ${Math.round(result.max_load)} Н<br><br>
            <ul style="padding-left: 20px; font-size: 14px; color: #444; margin-top: 10px;">${recsHtml}</ul>
        `;

        if (chart) chart.destroy();
        chart = new Chart(document.getElementById('loadChart'), {
            type: 'line',
            data: {
                labels: result.time_data.map(t => t.toFixed(2)),
                datasets: [{ 
                    label: 'Динамика нагрузки (Н)', 
                    data: result.load_data, 
                    borderColor: '#1e3c72',
                    backgroundColor: 'rgba(30, 60, 114, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });

    } catch (error) {
        console.error("Ошибка:", error);
        alert("Произошла ошибка биомеханики:\n" + error.message);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
};

// ==========================================
// ЧАСТЬ 2: МКЭ И 3D (THREE.JS)
// ==========================================

let geometryOffsets = { x: 0, y: 0, z: 0 };

const container = document.getElementById('viewer3d');
const initWidth = container.clientWidth || window.innerWidth / 2;
const initHeight = container.clientHeight || 600;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1e293b); 

const camera = new THREE.PerspectiveCamera(45, initWidth / initHeight, 0.1, 10000);
camera.position.set(300, 200, 300);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(initWidth, initHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI / 2 + 0.1; 

scene.add(new THREE.AmbientLight(0xffffff, 0.8));
const dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(200, 500, 200);
scene.add(dirLight);

const grid = new THREE.GridHelper(400, 40, 0x666666, 0x2a3b4c);
scene.add(grid);

function createTextSprite(text) {
    const canvas = document.createElement('canvas');
    canvas.width = 128; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'transparent';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = 'bold 20px Arial';
    ctx.fillStyle = '#8892b0'; 
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(30, 15, 1);
    return sprite;
}

for (let i = -200; i <= 200; i += 50) {
    if (i === 0) continue;
    let spriteX = createTextSprite(i + ' мм');
    spriteX.position.set(i, 0, 20); 
    scene.add(spriteX);

    let spriteZ = createTextSprite(i + ' мм');
    spriteZ.position.set(20, 0, i);
    scene.add(spriteZ);
}

const modelGroup = new THREE.Group();
modelGroup.rotation.x = -Math.PI / 2; 
scene.add(modelGroup);

let currentMesh = null;
let helpersGroup = new THREE.Group();
modelGroup.add(helpersGroup);

const resizeObserver = new ResizeObserver(() => {
    if (container.clientWidth === 0 || container.clientHeight === 0) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});
resizeObserver.observe(container);

document.getElementById('stlInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    const btn = document.getElementById('calcBtn');
    btn.textContent = "Загрузка...";
    
    // Прячем легенду при загрузке новой модели
    document.getElementById('legendOverlay').classList.add('hidden');
    document.getElementById('resText').innerHTML = "Ожидание запуска МКЭ...";

    reader.onload = function(event) {
        if (currentMesh) modelGroup.remove(currentMesh);
        helpersGroup.clear();

        const loader = new STLLoader();
        const geometry = loader.parse(event.target.result);
        
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        
        geometryOffsets.x = -(box.max.x + box.min.x) / 2;
        geometryOffsets.y = -(box.max.y + box.min.y) / 2;
        geometryOffsets.z = -box.min.z; 

        geometry.translate(geometryOffsets.x, geometryOffsets.y, geometryOffsets.z);
        geometry.computeVertexNormals();

        geometry.setAttribute('originalPosition', geometry.attributes.position.clone());

        const material = new THREE.MeshStandardMaterial({ color: 0xaaaaaa, roughness: 0.5 });
        currentMesh = new THREE.Mesh(geometry, material);
        modelGroup.add(currentMesh);

        const center = new THREE.Vector3(0, 0, (box.max.z - box.min.z) / 2);
        controls.target.copy(center.applyMatrix4(modelGroup.matrixWorld));
        
        btn.textContent = "Запустить Solver";
        btn.disabled = false;
    };
    reader.readAsArrayBuffer(file);
});

document.getElementById('calcBtn').addEventListener('click', async () => {
    const fileInput = document.getElementById('stlInput');
    const btn = document.getElementById('calcBtn');
    
    const progContainer = document.getElementById('progressContainer');
    const progBar = document.getElementById('progressBar');
    const progText = document.getElementById('progressText');
    const progPercent = document.getElementById('progressPercent');
    
    if (!fileInput.files.length) { alert("Сначала загрузите STL модель!"); return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('load_newtons', document.getElementById('loadInput').value);
    formData.append('condition', document.getElementById('gostCondition').value);

    btn.textContent = "Идет расчет...";
    btn.disabled = true;
    
    // Скрываем легенду на время расчета
    document.getElementById('legendOverlay').classList.add('hidden');
    
    if(progContainer) {
        progContainer.classList.remove('hidden');
        progBar.style.width = '0%';
        progBar.style.background = 'linear-gradient(90deg, var(--light-blue), var(--blue))';
    }
    
    let progress = 0;
    // Уменьшаем интервал до 200 мс, так как CalculiX считает очень быстро
    const progressInterval = setInterval(() => {
        if (progress < 95) {
            // Ускоряем заполнение шкалы
            let increment = progress < 30 ? 4 : (progress < 80 ? 2 : 0.5);
            progress += increment;
            
            if(progBar) progBar.style.width = `${progress}%`;
            if(progPercent) progPercent.textContent = `${Math.floor(progress)}%`;
            
            // Новые актуальные статусы для пайплайна CalculiX
            if(progText) {
                if (progress < 25) progText.textContent = "Подготовка 3D-сетки (PyVista , Gmsh)...";
                else if (progress < 45) progText.textContent = "Анализ нормалей и векторов...";
                else if (progress < 85) progText.textContent = "Расчет в CalculiX (SPOOLES/PaStiX)...";
                else progText.textContent = "Чтение результатов (.dat)...";
            }
        }
    }, 200);

    try {
        const response = await fetch('/api/calculate', { method: 'POST', body: formData });
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        
        clearInterval(progressInterval);
        if(progContainer) {
            progText.textContent = "Рендеринг...";
            progBar.style.width = '100%';
            progPercent.textContent = '100%';
        }
        
        if (data.status === "success") {
            btn.textContent = `Успех! (см. результаты)`;
            
            // --- ВЫВОД РЕЗУЛЬТАТОВ В UI ---
            // 1. Показываем легенду градиента
            const maxVal = data.max_stress;
            document.getElementById('legendMax').textContent = maxVal.toFixed(2);
            document.getElementById('legendMid').textContent = (maxVal / 2).toFixed(2);
            document.getElementById('legendOverlay').classList.remove('hidden');

            // 2. Выводим текст в боковое меню
            const conditionText = document.getElementById('gostCondition').options[document.getElementById('gostCondition').selectedIndex].text;
            const resSummary = document.getElementById('resText');
            resSummary.innerHTML = `
                <div style="background: #eef2f5; padding: 10px; border-radius: 6px; border-left: 4px solid var(--blue);">
                    <b>Решатель:</b> CalculiX (MUMPS/SPOOLES)<br>
                    <b>Режим:</b> ${conditionText}<br>
                    <hr style="border: 0; border-top: 1px solid #ccc; margin: 8px 0;">
                    <b>Максимальное значение:</b> <span style="color: red; font-weight: bold; font-size: 16px;">${maxVal.toFixed(2)}</span>
                </div>
            `;
            // -------------------------------
            if (data.stats) {
                document.getElementById('techReport').classList.remove('hidden');
                document.getElementById('statNodes').textContent = data.stats.nodes_count.toLocaleString();
                document.getElementById('statElems').textContent = data.stats.elements_count.toLocaleString();
                document.getElementById('statSlaves').textContent = data.stats.slave_nodes_count;
                document.getElementById('statType').textContent = data.stats.element_type;
                document.getElementById('statTime').textContent = data.stats.solve_time + " сек";
            }
            
            const geometry = currentMesh.geometry;
            const positions = geometry.attributes.position;
            const origPositions = geometry.attributes.originalPosition;
            const colors = new Float32Array(origPositions.count * 3);
            
            const SCALE = 4.0; 

            for (let i = 0; i < origPositions.count; i++) {
                const vx = origPositions.getX(i) - geometryOffsets.x;
                const vy = origPositions.getY(i) - geometryOffsets.y;
                const vz = origPositions.getZ(i) - geometryOffsets.z;

                let minDistSq = Infinity;
                let val = 0;
                let dx = 0, dy = 0, dz = 0;

                for (let j = 0; j < data.fem_nodes.length; j += 5) { 
                    const diffX = vx - data.fem_nodes[j][0];
                    const diffY = vy - data.fem_nodes[j][1];
                    const diffZ = vz - data.fem_nodes[j][2];
                    const d2 = diffX*diffX + diffY*diffY + diffZ*diffZ;
                    
                    if (d2 < minDistSq) { 
                        minDistSq = d2; 
                        val = data.fem_values[j]; 
                        if(data.displacements) {
                            dx = data.displacements[j][0];
                            dy = data.displacements[j][1];
                            dz = data.displacements[j][2];
                        }
                    }
                }

                positions.setXYZ(
                    i, 
                    origPositions.getX(i) + dx * SCALE, 
                    origPositions.getY(i) + dy * SCALE, 
                    origPositions.getZ(i) + dz * SCALE
                );

                const hue = (1 - Math.min(val / data.max_stress, 1)) * 240;
                const c = new THREE.Color(`hsl(${hue}, 100%, 50%)`);
                colors[i*3] = c.r; colors[i*3+1] = c.g; colors[i*3+2] = c.b;
            }

            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            positions.needsUpdate = true;
            currentMesh.material.vertexColors = true;
            currentMesh.material.color.setHex(0xffffff);
            currentMesh.material.needsUpdate = true;

            helpersGroup.clear();
            
            if (data.bottom_coords && data.bottom_coords.length > 0) {
                const markerGeo = new THREE.BoxGeometry(2, 2, 2); 
                const markerMat = new THREE.MeshBasicMaterial({ color: 0xff0000 });
                const markerMesh = new THREE.InstancedMesh(markerGeo, markerMat, data.bottom_coords.length);
                const dummy = new THREE.Object3D();
                for (let i = 0; i < data.bottom_coords.length; i++) {
                    dummy.position.set(
                        data.bottom_coords[i][0] + geometryOffsets.x, 
                        data.bottom_coords[i][1] + geometryOffsets.y, 
                        data.bottom_coords[i][2] + geometryOffsets.z
                    );
                    dummy.updateMatrix();
                    markerMesh.setMatrixAt(i, dummy.matrix);
                }
                markerMesh.instanceMatrix.needsUpdate = true;
                helpersGroup.add(markerMesh);
            }

            if (data.top_coords && data.top_coords.length > 0 && data.master_coords) {
                const slaveGeo = new THREE.SphereGeometry(1.0, 8, 8); 
                const slaveMat = new THREE.MeshBasicMaterial({ color: 0x00ffff, transparent: true, opacity: 0.6 }); 
                const slaveMesh = new THREE.InstancedMesh(slaveGeo, slaveMat, data.top_coords.length);
                const dummy = new THREE.Object3D();
                
                for (let i = 0; i < data.top_coords.length; i++) {
                    dummy.position.set(
                        data.top_coords[i][0] + geometryOffsets.x, 
                        data.top_coords[i][1] + geometryOffsets.y, 
                        data.top_coords[i][2] + geometryOffsets.z
                    );
                    dummy.updateMatrix();
                    slaveMesh.setMatrixAt(i, dummy.matrix);
                }
                slaveMesh.instanceMatrix.needsUpdate = true;
                helpersGroup.add(slaveMesh); 

                const masterPos = new THREE.Vector3(
                    data.master_coords[0] + geometryOffsets.x,
                    data.master_coords[1] + geometryOffsets.y,
                    data.master_coords[2] + geometryOffsets.z 
                );

                const lineMat = new THREE.LineBasicMaterial({ color: 0xffaa00, transparent: true, opacity: 0.1 }); 
                data.top_coords.forEach((p, idx) => {
                    if (idx % 15 !== 0) return;
                    const pLocal = new THREE.Vector3(p[0] + geometryOffsets.x, p[1] + geometryOffsets.y, p[2] + geometryOffsets.z);
                    const lineGeo = new THREE.BufferGeometry().setFromPoints([masterPos, pLocal]);
                    helpersGroup.add(new THREE.Line(lineGeo, lineMat));
                });

                if (data.force_vector) {
                    const dir = new THREE.Vector3(
                        data.force_vector[0], 
                        data.force_vector[1], 
                        data.force_vector[2]
                    );
                    dir.normalize(); 
                    const arrow = new THREE.ArrowHelper(dir, masterPos, 70, 0xff0000, 15, 8);
                    helpersGroup.add(arrow);
                }
            }
        }
        if(progContainer) setTimeout(() => progContainer.classList.add('hidden'), 2000);
    } catch (e) { 
        clearInterval(progressInterval);
        if(progBar) progBar.style.background = 'red';
        if(progText) progText.textContent = "Ошибка расчета!";
        console.error(e);
        alert("Ошибка МКЭ:\n" + e.message); 
    } finally {
        setTimeout(() => { if (!btn.disabled) btn.textContent = "Запустить Solver"; }, 3000);
        btn.disabled = false;
    }
});

function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }
animate();