const input = document.getElementById('video-input');
const dropzone = document.getElementById('dropzone');
const uploadPanel = document.getElementById('upload-panel');
const videoPanel = document.getElementById('video-panel');
const preparePanel = document.getElementById('prepare-panel');
const video = document.getElementById('video');
const videoStage = document.getElementById('video-stage');
const marker = document.getElementById('target-marker');
const selectedTime = document.getElementById('selected-time');
const selectedPosition = document.getElementById('selected-position');
const clearSelection = document.getElementById('clear-selection');
const fileMeta = document.getElementById('file-meta');
const payloadPreview = document.getElementById('payload-preview');
const summaryFile = document.getElementById('summary-file');
const summaryDuration = document.getElementById('summary-duration');
const summaryTime = document.getElementById('summary-time');
const steps = {
  upload: document.getElementById('step-upload'),
  player: document.getElementById('step-player'),
  ready: document.getElementById('step-ready'),
};

let currentFile = null;
let objectUrl = null;
let target = null;

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '—';
  const min = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${min}:${sec}`;
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
}

function activateStep(name) {
  Object.values(steps).forEach((step) => step.classList.remove('active'));
  steps[name].classList.add('active');
}

function resetTarget() {
  target = null;
  marker.classList.add('hidden');
  selectedTime.textContent = '—';
  selectedPosition.textContent = '—';
  clearSelection.disabled = true;
  preparePanel.classList.add('hidden');
  activateStep('player');
}

function preparePayload() {
  if (!currentFile || !target) return;
  const payload = {
    input: {
      video_url: '<URL_SIGNEE_GENEREE_PAR_LE_BACKEND>',
      target: {
        x: Number(target.x.toFixed(4)),
        y: Number(target.y.toFixed(4)),
      },
      target_time_seconds: Number(target.time.toFixed(2)),
      sample_fps: 5,
      confidence: 0.22,
      image_size: 960,
    },
  };
  payloadPreview.textContent = JSON.stringify(payload, null, 2);
  summaryFile.textContent = currentFile.name;
  summaryDuration.textContent = formatTime(video.duration);
  summaryTime.textContent = formatTime(target.time);
  preparePanel.classList.remove('hidden');
  activateStep('ready');
}

function loadVideoFile(file) {
  if (!file || !file.type.startsWith('video/')) {
    alert('Choisis un fichier vidéo valide.');
    return;
  }
  currentFile = file;
  target = null;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(file);
  video.src = objectUrl;
  fileMeta.textContent = `${file.name} · ${formatBytes(file.size)}`;
  uploadPanel.classList.add('hidden');
  videoPanel.classList.remove('hidden');
  preparePanel.classList.add('hidden');
  activateStep('player');
  resetTarget();
}

input.addEventListener('change', (event) => {
  loadVideoFile(event.target.files?.[0]);
});

['dragenter', 'dragover'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add('dragging');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove('dragging');
  });
});

dropzone.addEventListener('drop', (event) => {
  loadVideoFile(event.dataTransfer?.files?.[0]);
});

video.addEventListener('loadedmetadata', () => {
  fileMeta.textContent = `${currentFile.name} · ${formatBytes(currentFile.size)} · ${formatTime(video.duration)}`;
});

videoStage.addEventListener('click', (event) => {
  if (!currentFile || video.readyState < 2) return;

  const rect = video.getBoundingClientRect();
  const videoRatio = video.videoWidth / video.videoHeight;
  const elementRatio = rect.width / rect.height;

  let renderedWidth = rect.width;
  let renderedHeight = rect.height;
  let offsetX = 0;
  let offsetY = 0;

  if (elementRatio > videoRatio) {
    renderedWidth = rect.height * videoRatio;
    offsetX = (rect.width - renderedWidth) / 2;
  } else {
    renderedHeight = rect.width / videoRatio;
    offsetY = (rect.height - renderedHeight) / 2;
  }

  const x = event.clientX - rect.left - offsetX;
  const y = event.clientY - rect.top - offsetY;
  if (x < 0 || y < 0 || x > renderedWidth || y > renderedHeight) return;

  const normalizedX = x / renderedWidth;
  const normalizedY = y / renderedHeight;
  target = {
    x: normalizedX,
    y: normalizedY,
    time: video.currentTime,
  };

  marker.style.left = `${offsetX + x}px`;
  marker.style.top = `${offsetY + y}px`;
  marker.classList.remove('hidden');
  selectedTime.textContent = formatTime(target.time);
  selectedPosition.textContent = `x ${normalizedX.toFixed(3)} · y ${normalizedY.toFixed(3)}`;
  clearSelection.disabled = false;
  video.pause();
  preparePayload();
});

clearSelection.addEventListener('click', resetTarget);

window.addEventListener('beforeunload', () => {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
});
