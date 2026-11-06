const form = document.querySelector('#generateForm');
const promptInput = document.querySelector('#prompt');
const charCount = document.querySelector('#charCount');
const button = document.querySelector('#generateButton');
const errorBox = document.querySelector('#formError');
const emptyState = document.querySelector('#emptyState');
const progressState = document.querySelector('#progressState');
const videoState = document.querySelector('#videoState');
const progressBar = document.querySelector('#progressBar');
const progressValue = document.querySelector('#progressValue');
const progressMessage = document.querySelector('#progressMessage');
const resultVideo = document.querySelector('#resultVideo');
const downloadLink = document.querySelector('#downloadLink');
const elapsedTime = document.querySelector('#elapsedTime');

promptInput.addEventListener('input', () => { charCount.textContent = `${promptInput.value.length} / 4000`; });

async function checkHealth() {
  try {
    const data = await fetch('/api/health').then(r => r.json());
    document.querySelector('#healthDot').classList.toggle('online', data.comfyui);
    document.querySelector('#healthText').textContent = data.comfyui ? 'GPU sẵn sàng' : 'ComfyUI offline';
  } catch { document.querySelector('#healthText').textContent = 'Backend offline'; }
}

function showProgress() {
  emptyState.classList.add('hidden'); videoState.classList.add('hidden'); progressState.classList.remove('hidden');
  button.disabled = true; errorBox.textContent = '';
}

async function poll(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) throw new Error('Không đọc được trạng thái render');
  const job = await response.json();
  progressBar.style.width = `${job.progress}%`;
  progressValue.textContent = `${job.progress}%`;
  progressMessage.textContent = job.message;
  if (job.status === 'success') {
    progressState.classList.add('hidden'); videoState.classList.remove('hidden');
    const videoUrl = `${job.video_url}?t=${Date.now()}`;
    resultVideo.src = videoUrl; downloadLink.href = videoUrl;
    elapsedTime.textContent = `${job.elapsed_seconds} giây xử lý`;
    button.disabled = false; return;
  }
  if (job.status === 'error') throw new Error(job.message);
  setTimeout(() => poll(jobId).catch(showError), 1800);
}

function showError(error) {
  progressState.classList.add('hidden'); emptyState.classList.remove('hidden');
  button.disabled = false; errorBox.textContent = error.message || String(error);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault(); showProgress();
  const seedText = document.querySelector('#seed').value.trim();
  try {
    const response = await fetch('/api/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ prompt:promptInput.value, duration:Number(document.querySelector('#duration').value), seed:seedText ? Number(seedText) : null })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Không thể tạo job');
    poll(data.id).catch(showError);
  } catch (error) { showError(error); }
});

checkHealth(); setInterval(checkHealth, 15000);

