import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

// ==========================================
// ЧАСТЬ 1: БИОМЕХАНИКА И ГРАФИКИ (CHART.JS)
// ==========================================

let chart = null;

// Делаем функцию глобальной, чтобы ее видела кнопка из HTML (onclick="runBioAnalysis()")
window.runBioAnalysis = async () => {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = "Считаем...";
    btn.disabled = true;

    try {
        const data = {
            weight: parseFloat(document.getElementById('weight').value) || 80,
            thigh_girth: 55, // Заглушка (пока не используется в новой логике)
            movement_type: document.getElementById('moveType').value
        };

        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (!res.ok) {
            const errText = await res.text();
            throw new Error(`Ошибка сервера: ${errText}`);
        }

        const result = await res.json();
        
        // --- МАГИЯ СЛИЯНИЯ ---
        // Передаем рассчитанный пик нагрузки прямо в твой МКЭ-инпут!
        document.getElementById('loadInput').value = Math.round(result.max_load);
        
        // Выводим результаты
        const recsHtml = result.recommendations.map(r => `<li style="margin-bottom: 5px;">${r}</li>`).join('');
        const lifeColor = result.service_life < 2 ? 'red' : 'green';
        
        document.getElementById('resText').innerHTML = `
            <b>Срок службы:</b> <span style="color: ${lifeColor}">${result.service_life} лет</span><br>
            <b>Пиковая нагрузка:</b> ${Math.round(result.max_load)} Н<br><br>
            <ul style="padding-left: 20px; font-size: 14px; color: #444; margin-top: 10px;">${recsHtml}</ul>
        `;

        // Рисуем график
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
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });

    } catch (error) {
        console.error("Ошибка аналитики:", error);
        alert("Произошла ошибка при расчете биомеханики:\n" + error.message);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
};


// ==========================================
// ЧАСТЬ 2: 3D ВИЗУАЛИЗАЦИЯ И МКЭ (THREE.JS)
// ==========================================

const container = document.getElementById('viewer3d');

// Защита от белого экрана
const initWidth = container.clientWidth || window.innerWidth / 2;
const initHeight = container.clientHeight || 600;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf0f2f5); // Светлый фон под стать дашборду

const camera = new THREE.PerspectiveCamera(45, initWidth / initHeight, 0.1, 10000);
camera.position.set(200, 200, 200);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(initWidth, initHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// Свет и сетка
scene.add(new THREE.GridHelper(500, 50, 0xcccccc, 0xcccccc));
scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(100, 200, 100);
scene.add(dirLight);

// Группа для модели (сразу поворачиваем, чтобы гильза стояла вертикально)
const modelGroup = new THREE.Group();
modelGroup.rotation.x = -Math.PI / 2;
scene.add(modelGroup);

let currentMesh = null;
let helpersGroup = new THREE.Group();
modelGroup.add(helpersGroup); 

// Следим за размерами окна (Особенно важно при переключении вкладок!)
const resizeObserver = new ResizeObserver(() => {
    if (container.clientWidth === 0 || container.clientHeight === 0) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});
resizeObserver.observe(container);

// Утилиты
function fitCameraToMesh(mesh) {
    const box = new THREE.Box3().setFromObject(mesh);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
    camera.position.set(center.x + cameraZ * 1.5, center.y + cameraZ * 1.5, center.z + cameraZ * 1.5);
    controls.target.copy(center);
    controls.update();
}

function getHeatmapColor(value, min, max) {
    let norm = (value - min) / (max - min);
    norm = Math.max(0, Math.min(1, norm));
    const hue = (1 - norm) * 240; // От синего (240) до красного (0)
    return new THREE.Color(`hsl(${hue}, 100%, 50%)`);
}

// Загрузка STL
document.getElementById('stlInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    const btn = document.getElementById('calcBtn');
    btn.textContent = "Загрузка...";

    reader.onload = function(event) {
        if (currentMesh) modelGroup.remove(currentMesh);
        helpersGroup.clear(); 

        const loader = new STLLoader();
        const geometry = loader.parse(event.target.result);
        geometry.computeVertexNormals(); 

        const material = new THREE.MeshStandardMaterial({ 
            color: 0xcccccc, roughness: 0.4 
        });
        
        currentMesh = new THREE.Mesh(geometry, material);
        modelGroup.add(currentMesh); 

        fitCameraToMesh(modelGroup); 
        btn.textContent = "Запустить Solver";
        btn.disabled = false;
    };
    reader.readAsArrayBuffer(file);
});

// Отправка на расчет МКЭ
// Отправка на расчет МКЭ
document.getElementById('calcBtn').addEventListener('click', async () => {
    const fileInput = document.getElementById('stlInput');
    const loadInput = document.getElementById('loadInput');
    const btn = document.getElementById('calcBtn');
    
    // Элементы прогресс-бара
    const progContainer = document.getElementById('progressContainer');
    const progBar = document.getElementById('progressBar');
    const progText = document.getElementById('progressText');
    const progPercent = document.getElementById('progressPercent');
    
    if (!fileInput.files.length) {
        alert("Сначала загрузите STL модель!");
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('load_newtons', loadInput.value);
    formData.append('offset_x', document.getElementById('offsetX').value);
    formData.append('offset_y', document.getElementById('offsetY').value); 

    btn.textContent = "Идет расчет...";
    btn.disabled = true;
    
    // --- ЗАПУСК ПРОГРЕСС-БАРА ---
    progContainer.classList.remove('hidden');
    progBar.style.width = '0%';
    progBar.style.background = 'linear-gradient(90deg, var(--light-blue), var(--blue))';
    let progress = 0;
    
    const progressInterval = setInterval(() => {
        if (progress < 95) {
            // Эмулируем этапы: Сетка (0-20%), Матрицы (20-75%), СЛАУ (75-95%)
            let increment = progress < 20 ? 3 : (progress < 75 ? 1 : 0.5);
            progress += increment;
            
            progBar.style.width = `${progress}%`;
            progPercent.textContent = `${Math.floor(progress)}%`;

            if (progress < 20) progText.textContent = "Генерация 3D сетки (Gmsh)...";
            else if (progress < 75) progText.textContent = "Сборка глобальной матрицы...";
            else progText.textContent = "Решение СЛАУ (Ku=F)...";
        }
    }, 500); // Обновляем каждые полсекунды

    try {
        const response = await fetch('/api/calculate', { method: 'POST', body: formData });
        
        if (!response.ok) throw new Error(`Ошибка сервера: ${await response.text()}`);
        const data = await response.json();
        
        if (data.status === "success") {
            // --- УСПЕХ: Заполняем до 100% ---
            clearInterval(progressInterval);
            progText.textContent = "Рендеринг результатов...";
            progBar.style.width = '100%';
            progPercent.textContent = '100%';
            
            btn.textContent = `Успех! Деформация: ${data.max_stress} мм`;
            
            // Раскраска (Heatmap)
            const geometry = currentMesh.geometry;
            const positions = geometry.attributes.position;
            const colors = new Float32Array(positions.count * 3);
            
            for (let i = 0; i < positions.count; i++) {
                const vx = positions.getX(i);
                const vy = positions.getY(i);
                const vz = positions.getZ(i);

                let minDistSq = Infinity;
                let closestValue = 0;

                for (let j = 0; j < data.fem_nodes.length; j++) {
                    const dx = vx - data.fem_nodes[j][0];
                    const dy = vy - data.fem_nodes[j][1];
                    const dz = vz - data.fem_nodes[j][2];
                    const distSq = dx*dx + dy*dy + dz*dz; 
                    if (distSq < minDistSq) {
                        minDistSq = distSq;
                        closestValue = data.fem_values[j];
                    }
                }
                const color = getHeatmapColor(closestValue, 0, data.max_stress);
                colors[i*3] = color.r; colors[i*3+1] = color.g; colors[i*3+2] = color.b;
            }

            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            currentMesh.material.vertexColors = true;
            currentMesh.material.color.setHex(0xffffff);
            currentMesh.material.needsUpdate = true;

            helpersGroup.clear();

            // Визуализация заделки (Красные кубики дна)
            if (data.bottom_coords && data.bottom_coords.length > 0) {
                const markerGeo = new THREE.BoxGeometry(2, 2, 2); 
                const markerMat = new THREE.MeshBasicMaterial({ color: 0xff0000 });
                const markerMesh = new THREE.InstancedMesh(markerGeo, markerMat, data.bottom_coords.length);
                const dummy = new THREE.Object3D();
                
                for (let i = 0; i < data.bottom_coords.length; i++) {
                    dummy.position.set(data.bottom_coords[i][0], data.bottom_coords[i][1], data.bottom_coords[i][2]);
                    dummy.updateMatrix();
                    markerMesh.setMatrixAt(i, dummy.matrix);
                }
                markerMesh.instanceMatrix.needsUpdate = true;
                helpersGroup.add(markerMesh);
            }

            // Визуализация нагрузки (ГОСТ)
            if (data.top_coords && data.top_coords.length > 0) {
                let cx = 0, cy = 0, cz = 0;
                for (let i = 0; i < data.top_coords.length; i++) {
                    cx += data.top_coords[i][0];
                    cy += data.top_coords[i][1];
                    cz += data.top_coords[i][2];
                }
                const numTopNodes = data.top_coords.length;
                cx /= numTopNodes; cy /= numTopNodes; cz /= numTopNodes;

                const offX = parseFloat(document.getElementById('offsetX').value) || 0;
                const offY = parseFloat(document.getElementById('offsetY').value) || 0;

                const forceOrigin = new THREE.Vector3(cx + offX, cz + 50, cy + offY); 
                const forceDir = new THREE.Vector3(0, -1, 0); 
                
                const arrowHelper = new THREE.ArrowHelper(forceDir, forceOrigin, 50, 0xff0000, 15, 10);
                helpersGroup.add(arrowHelper);
                
                const lineMat = new THREE.LineBasicMaterial({ color: 0xffaa00, transparent: true, opacity: 0.3 });
                for (let i = 0; i < data.top_coords.length; i += 5) {
                    const pPts = [
                        forceOrigin, 
                        new THREE.Vector3(data.top_coords[i][0], data.top_coords[i][2], data.top_coords[i][1])
                    ];
                    const lineGeo = new THREE.BufferGeometry().setFromPoints(pPts);
                    helpersGroup.add(new THREE.Line(lineGeo, lineMat));
                }
            }

            // Прячем прогресс-бар через 2 секунды после успеха
            setTimeout(() => progContainer.classList.add('hidden'), 2000);
        }
    } catch (error) {
        clearInterval(progressInterval);
        progBar.style.background = 'red';
        progText.textContent = "Ошибка расчета!";
        console.error(error);
        alert("Ошибка МКЭ расчета:\n" + error.message);
        btn.textContent = "Ошибка";
    } finally {
        setTimeout(() => {
            if (!btn.disabled) btn.textContent = "Запустить Solver";
        }, 3000);
        btn.disabled = false;
    }
});

// Анимация
function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();