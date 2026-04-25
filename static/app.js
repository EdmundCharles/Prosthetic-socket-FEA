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
// Ограничим спуск камеры под пол, чтобы сетка всегда была внизу
controls.maxPolarAngle = Math.PI / 2 + 0.1; 

scene.add(new THREE.AmbientLight(0xffffff, 0.8));
const dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(200, 500, 200);
scene.add(dirLight);

// --- НОВОЕ: Оцифрованная размерная сетка ---
// Создаем сетку 400x400 мм (шаг 10 мм)
const grid = new THREE.GridHelper(400, 40, 0x666666, 0x2a3b4c);
scene.add(grid);

// Функция для создания текста, который всегда смотрит в камеру
function createTextSprite(text) {
    const canvas = document.createElement('canvas');
    canvas.width = 128; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'transparent';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = 'bold 20px Arial';
    ctx.fillStyle = '#8892b0'; // Серо-голубой цвет текста
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(30, 15, 1);
    return sprite;
}

// Расставляем метки масштаба каждые 50 мм по осям
for (let i = -200; i <= 200; i += 50) {
    if (i === 0) continue;
    let spriteX = createTextSprite(i + ' мм');
    spriteX.position.set(i, 0, 20); // Сдвиг от центральной оси
    scene.add(spriteX);

    let spriteZ = createTextSprite(i + ' мм');
    spriteZ.position.set(20, 0, i);
    scene.add(spriteZ);
}
// ------------------------------------------

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
        
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        
        geometryOffsets.x = -(box.max.x + box.min.x) / 2;
        geometryOffsets.y = -(box.max.y + box.min.y) / 2;
        geometryOffsets.z = -box.min.z; 

        geometry.translate(geometryOffsets.x, geometryOffsets.y, geometryOffsets.z);
        geometry.computeVertexNormals();

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

// Запуск МКЭ расчета
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
    formData.append('offset_x', document.getElementById('offsetX').value);
    formData.append('offset_y', document.getElementById('offsetY').value);

    btn.textContent = "Идет расчет...";
    btn.disabled = true;
    
    if(progContainer) {
        progContainer.classList.remove('hidden');
        progBar.style.width = '0%';
        progBar.style.background = 'linear-gradient(90deg, var(--light-blue), var(--blue))';
    }
    
    let progress = 0;
    const progressInterval = setInterval(() => {
        if (progress < 95) {
            let increment = progress < 20 ? 3 : (progress < 75 ? 1 : 0.5);
            progress += increment;
            if(progBar) progBar.style.width = `${progress}%`;
            if(progPercent) progPercent.textContent = `${Math.floor(progress)}%`;
            if(progText) {
                if (progress < 20) progText.textContent = "Генерация 3D сетки (Gmsh)...";
                else if (progress < 75) progText.textContent = "Сборка глобальной матрицы...";
                else progText.textContent = "Решение СЛАУ (Ku=F)...";
            }
        }
    }, 500);

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
            btn.textContent = `Успех! Макс. смещение: ${data.max_stress} мм`;
            
            // Раскраска тепловой карты
            const geometry = currentMesh.geometry;
            const positions = geometry.attributes.position;
            const colors = new Float32Array(positions.count * 3);
            
            for (let i = 0; i < positions.count; i++) {
                const vx = positions.getX(i) - geometryOffsets.x;
                const vy = positions.getY(i) - geometryOffsets.y;
                const vz = positions.getZ(i) - geometryOffsets.z;

                let minDistSq = Infinity;
                let val = 0;
                for (let j = 0; j < data.fem_nodes.length; j+=5) { 
                    const dx = vx - data.fem_nodes[j][0];
                    const dy = vy - data.fem_nodes[j][1];
                    const dz = vz - data.fem_nodes[j][2];
                    const d2 = dx*dx + dy*dy + dz*dz;
                    if (d2 < minDistSq) { minDistSq = d2; val = data.fem_values[j]; }
                }
                const hue = (1 - Math.min(val/data.max_stress, 1)) * 240;
                const c = new THREE.Color(`hsl(${hue}, 100%, 50%)`);
                colors[i*3] = c.r; colors[i*3+1] = c.g; colors[i*3+2] = c.b;
            }
            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            currentMesh.material.vertexColors = true;
            currentMesh.material.color.setHex(0xffffff);
            currentMesh.material.needsUpdate = true;

            helpersGroup.clear();
            
            // 1. Рисуем заделку (Красные кубики дна)
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

            // --- НОВОЕ: 2. Выделяем Slave-узлы (Голубые сферы) ---
            // --- НОВОЕ: 2. Выделяем Slave-узлы (Внутренний имитатор культи) ---
            if (data.top_coords && data.top_coords.length > 0) {
                const slaveGeo = new THREE.SphereGeometry(1.0, 8, 8); // Сферы чуть меньше
                const slaveMat = new THREE.MeshBasicMaterial({ color: 0x00ffff, transparent: true, opacity: 0.6 }); 
                const slaveMesh = new THREE.InstancedMesh(slaveGeo, slaveMat, data.top_coords.length);
                const dummy = new THREE.Object3D();
                
                let tcx = 0, tcy = 0, tcz = 0;
                
                for (let i = 0; i < data.top_coords.length; i++) {
                    // Для расчета центра Мастер-узла берем только самые верхние точки
                    if (i < 50) { 
                        tcx += data.top_coords[i][0]; 
                        tcy += data.top_coords[i][1]; 
                    }
                    
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

                // 3. Высчитываем Мастер-узел
                tcx /= 50; 
                tcy /= 50; 
                
                const offX = parseFloat(document.getElementById('offsetX').value) || 0;
                const offY = parseFloat(document.getElementById('offsetY').value) || 0;
                
                // Находим самую высокую точку Z для Мастер-узла
                let maxZ = -Infinity;
                data.top_coords.forEach(p => { if(p[2] > maxZ) maxZ = p[2]; });

                const masterPos = new THREE.Vector3(
                    tcx + offX + geometryOffsets.x,
                    tcy + offY + geometryOffsets.y,
                    maxZ + 50 + geometryOffsets.z 
                );

                // Полупрозрачная "паутина" RBE2 связей, уходящая вглубь
                const lineMat = new THREE.LineBasicMaterial({ color: 0xffaa00, transparent: true, opacity: 0.1 }); // Делаем прозрачнее
                data.top_coords.forEach((p, idx) => {
                    // Рисуем только каждую 15-ю связь, чтобы создать красивый эффект голограммы
                    if (idx % 15 !== 0) return;
                    const pLocal = new THREE.Vector3(p[0] + geometryOffsets.x, p[1] + geometryOffsets.y, p[2] + geometryOffsets.z);
                    const lineGeo = new THREE.BufferGeometry().setFromPoints([masterPos, pLocal]);
                    helpersGroup.add(new THREE.Line(lineGeo, lineMat));
                });

                // Красный вектор пресса
                const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), masterPos, 60, 0xff0000, 15, 8);
                helpersGroup.add(arrow);
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