const steps = [
  ['downloading', 'Downloading video'],
  ['processing_video', 'Processing video'],
  ['transcription', 'Whisper transcription running'],
  ['ai_analysis', 'AI analyzing viral moments'],
  ['cutting_clips', 'Cutting clips'],
  ['completed', 'Clips ready'],
];

const state = { pollTimer: null, jobId: null };
const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  "'": '&#39;',
  '"': '&quot;',
}[char]));

const form = $('#processForm');
const urlInput = $('#urlInput');
const generateButton = $('#generateButton');
const homeScreen = $('#homeScreen');
const processingScreen = $('#processingScreen');
const resultsScreen = $('#resultsScreen');
const progressFill = $('#progressFill');
const progressPercent = $('#progressPercent');
const currentDetail = $('#currentDetail');
const stepList = $('#stepList');
const activityLog = $('#activityLog');
const resultsGrid = $('#resultsGrid');
const errorModal = $('#errorModal');
const errorText = $('#errorText');

function renderSteps(activeStep) {
  const activeIndex = steps.findIndex(([key]) => key === activeStep);
  stepList.innerHTML = steps.map(([key, label], index) => {
    const icon = index < activeIndex || activeStep === 'completed' ? '✔' : index === activeIndex ? '→' : '•';
    const className = index < activeIndex || activeStep === 'completed' ? 'done' : index === activeIndex ? 'active' : '';
    return `<li class="${className}"><span>${icon}</span><span>${label}</span></li>`;
  }).join('');
}

function showScreen(screen) {
  [homeScreen, processingScreen, resultsScreen].forEach((item) => item.classList.add('hidden'));
  screen.classList.remove('hidden');
}

function updateStatus(job) {
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  progressFill.style.width = `${progress}%`;
  progressPercent.textContent = `${progress}%`;
  currentDetail.textContent = job.detail || job.step || 'Working';
  renderSteps(job.step);
  activityLog.innerHTML = (job.log || []).slice(-8).map((entry) => `<li>${escapeHTML(entry)}</li>`).join('');

  if (job.status === 'completed') {
    stopPolling();
    renderResults(job.clips || []);
  }
  if (job.status === 'failed') {
    stopPolling();
    showError(job.error || 'Processing failed. Check the Termux server logs.');
    generateButton.disabled = false;
  }
}

function renderResults(clips) {
  resultsGrid.innerHTML = clips.map((clip, index) => `
    <article class="clip-card">
      <video src="${escapeHTML(clip)}" controls preload="metadata"></video>
      <a href="${escapeHTML(clip)}" download>Download clip ${index + 1}</a>
    </article>
  `).join('');
  showScreen(resultsScreen);
  generateButton.disabled = false;
}

function stopPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function pollStatus() {
  if (!state.jobId) return;
  const response = await fetch(`/status/${state.jobId}`);
  if (!response.ok) throw new Error('Could not fetch job status');
  updateStatus(await response.json());
}

function startPolling() {
  stopPolling();
  state.pollTimer = window.setInterval(() => pollStatus().catch((error) => showError(error.message)), 1200);
}

function showError(message) {
  errorText.textContent = message;
  if (typeof errorModal.showModal === 'function') errorModal.showModal();
  else window.alert(message);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  generateButton.disabled = true;
  showScreen(processingScreen);
  renderSteps('queued');
  updateStatus({ progress: 0, detail: 'Queued', step: 'queued', log: ['Job queued'] });

  try {
    const response = await fetch('/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: urlInput.value.trim() }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to create processing job');
    }
    const job = await response.json();
    state.jobId = job.job_id;
    updateStatus(job);
    startPolling();
  } catch (error) {
    generateButton.disabled = false;
    showScreen(homeScreen);
    showError(error.message);
  }
});

$('#newJobButton').addEventListener('click', () => {
  stopPolling();
  state.jobId = null;
  form.reset();
  showScreen(homeScreen);
});

$('#closeErrorButton').addEventListener('click', () => errorModal.close());
renderSteps('queued');
