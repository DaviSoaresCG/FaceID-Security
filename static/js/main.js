document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('video-element');
    const canvas = document.getElementById('canvas-overlay');
    const statusText = document.getElementById('status-text');
    const resultsDiv = document.getElementById('results-div');
    
    let isRecognizing = false;
    let stream = null;

    if (video && canvas) {
        // We are on the webcam page
        startWebcam();
    }

    async function startWebcam() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
            
            // Wait for video to start playing to get correct dimensions
            video.addEventListener('loadedmetadata', () => {
                video.play();
                // Match canvas size to video size
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                statusText.innerText = "Webcam ativa. Iniciando reconhecimento...";
                statusText.className = "text-success";
                
                // Start sending frames
                isRecognizing = true;
                processFrame();
            });
        } catch (err) {
            console.error("Erro ao acessar webcam:", err);
            statusText.innerText = "Erro ao acessar a webcam. Verifique as permissões.";
            statusText.className = "text-danger";
        }
    }

    async function processFrame() {
        if (!isRecognizing) return;

        // Draw current video frame to a temporary canvas to get base64
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = video.videoWidth;
        tempCanvas.height = video.videoHeight;
        const ctx = tempCanvas.getContext('2d');
        ctx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);
        
        // Convert to base64 jpeg
        const base64Image = tempCanvas.toDataURL('image/jpeg', 0.8);

        try {
            const response = await fetch('/api/reconhecer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ image: base64Image })
            });

            if (response.ok) {
                const data = await response.json();
                drawResults(data.rostos);
                updateResultsList(data.rostos);
            }
        } catch (error) {
            console.error("Erro na API de reconhecimento:", error);
        }

        // Loop after a small delay to avoid overwhelming the server
        setTimeout(processFrame, 500);
    }

    function drawResults(rostos) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height); // Clear previous

        if (!rostos || rostos.length === 0) return;

        rostos.forEach(rosto => {
            const box = rosto.box;
            // face_recognition returns: top, right, bottom, left
            const y = box.top;
            const x = box.left;
            const width = box.right - box.left;
            const height = box.bottom - box.top;

            // Draw bounding box
            ctx.beginPath();
            ctx.lineWidth = 3;
            ctx.strokeStyle = rosto.id ? '#10b981' : '#ef4444'; // Green if known, red if unknown
            ctx.rect(x, y, width, height);
            ctx.stroke();

            // Draw label background
            const label = `${rosto.nome} (${rosto.confianca})`;
            ctx.font = '16px Inter, Arial';
            const textWidth = ctx.measureText(label).width;
            
            ctx.fillStyle = rosto.id ? '#10b981' : '#ef4444';
            ctx.fillRect(x - 1.5, y - 25, textWidth + 10, 25);

            // Draw text
            ctx.fillStyle = '#ffffff';
            ctx.fillText(label, x + 3, y - 7);
        });
    }

    function updateResultsList(rostos) {
        if (!resultsDiv) return;
        
        if (!rostos || rostos.length === 0) {
            resultsDiv.innerHTML = '<p class="text-muted">Nenhum rosto detectado no momento.</p>';
            return;
        }

        let html = '<ul class="list-group list-group-flush bg-transparent">';
        rostos.forEach(rosto => {
            if(rosto.id) {
                html += `
                <li class="list-group-item bg-transparent text-light border-secondary">
                    <i class="bi bi-person-check text-success me-2"></i>
                    <strong>Nome:</strong> ${rosto.nome} <br>
                    <strong>ID:</strong> ${rosto.id} <br>
                    <strong>Confiança:</strong> ${rosto.confianca}
                </li>`;
            } else {
                html += `
                <li class="list-group-item bg-transparent text-light border-secondary">
                    <i class="bi bi-person-x text-danger me-2"></i>
                    Pessoa Desconhecida
                </li>`;
            }
        });
        html += '</ul>';
        resultsDiv.innerHTML = html;
    }
});
