/* ═══════════════════════════════════════════════════════════
   Manhwa Recap Maker V2 — App Controller
   State-machine wizard with two pipeline modes
   ═══════════════════════════════════════════════════════════ */

// ─── SocketIO ────────────────────────────────────────────
const socket = io({ transports: ['polling', 'websocket'] });

// ─── Global State ────────────────────────────────────────
const APP = {
  mode: 'full_recap',   // Single-purpose Manhwa Recap Studio
  currentStep: 0,
  projectName: '',
  sourceFolder: '',
  settings: {},
  projectData: null,    // fetched project state
  running: false,       // is a pipeline step running?
  steps: [],            // step definitions for current mode
  
  // User-selected batch mode (explicit toggle)
  
  // Chapter navigation for batch processing
  manhwaName: '',       // e.g., "Sword-Devouring-Swordmaster"
  currentChapter: 1,    // e.g., 1 (for Chapter_00001)
  isBatch: false,       // true if processing multiple chapters
  chapterList: [],      // e.g., [1, 2, 3, ...] for available chapters
};

// ─── Step Definitions ────────────────────────────────────
const FULL_RECAP_STEPS = [
  { id: 'source', label: 'Ссылка', title: 'Ссылка на мангу и главы', subtitle: 'Вставьте URL, выберите одну главу или диапазон глав' },
  { id: 'stitch', label: 'Кадры', title: 'Штатная обработка AniFlow', subtitle: 'Один проход обнаружения и вырезания панелей через существующий Crop 2' },
  { id: 'review', label: 'Проверка', title: 'Готовые панели', subtitle: 'Проверьте результат штатного извлечения изображений' },
  { id: 'extract_text', label: 'Контекст', title: 'Текст и описания', subtitle: 'Используйте уже извлечённый OCR-текст и описания сцен' },
  { id: 'full_script', label: 'Сценарий', title: 'Полный русский пересказ', subtitle: 'Сценарий в стиле выбранного профиля и заданного объёма' },
  { id: 'full_review', label: 'Редактор', title: 'Проверка сценария', subtitle: 'Исправьте текст; длительность видео пересчитается автоматически' },
  { id: 'full_video', label: 'Видео', title: 'Беззвучный видеоряд', subtitle: 'Нумерация всех готовых кадров и MP4 на 0,72 секунды на слово' },
  { id: 'full_package', label: 'YouTube', title: 'Упаковка ролика', subtitle: 'Три превью, три названия, описание и закреплённый комментарий' },
];

// ─── Init ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkStatus();
  loadProjects();
  setInterval(checkStatus, 60000);
});

// ─── Status Check ────────────────────────────────────────
async function checkStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    setDot('dotOllama', d.ollama?.running);
    setDot('dotFFmpeg', d.ffmpeg);
  } catch (e) { /* ignore */ }
}

function setDot(id, ok) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('on', !!ok);
}

// ─── Projects ────────────────────────────────────────────
async function loadProjects() {
  try {
    const response = await fetch('/api/projects');
    const projects = await response.json();
    renderProjects(projects);
  } catch (error) {
    console.warn('Could not load recent projects:', error);
  }
}

function renderProjects(projects) {
  const grid = document.getElementById('projectsGrid');
  if (!projects || projects.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-state-icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none" stroke="#1B1C1F" stroke-width="1.6" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="empty-state-text">Nothing on the desk yet. Pick a style above and start your first strip.</div>
      </div>`;
    return;
  }
  grid.innerHTML = projects.map(p => `
    <div class="project-card" onclick="resumeProject('${esc(p.name)}')">
      <div class="project-card-name">${esc(p.name)}</div>
      <div class="project-card-meta">${p.panels_count || 0} panels</div>
      <div class="project-card-stage">${p.stage || 'init'}</div>
    </div>`).join('');
}

function resumeProject(name) {
  // Load project and determine which mode it was using
  APP.projectName = name;
  // Default to dialogue mode for resume
  selectMode('full_recap');
  APP.currentStep = 2; // jump to review
  renderWizard();
  loadProjectData(name);
}

// ─── Mode Selection ──────────────────────────────────────
function selectMode(mode) {
  // This fork is a single-purpose application: only Full Recap Studio is exposed.
  APP.mode = 'full_recap';
  APP.steps = FULL_RECAP_STEPS;
  APP.currentStep = 0;
  APP.projectName = '';
  APP.sourceFolder = '';
  APP.projectData = null;
  // Persist the active pipeline mode so backend steps pick the right
  // panel list + text field (narration vs dialogue) for this project
  APP.settings.pipeline_mode = mode;

  document.getElementById('viewHome').classList.add('hidden');
  document.getElementById('viewWizard').classList.remove('hidden');
  renderWizard();
}
window.selectMode = selectMode; // Make sure it's globally accessible

function goHome() {
  APP.mode = null;
  APP.currentStep = 0;
  document.getElementById('viewHome').classList.remove('hidden');
  document.getElementById('viewWizard').classList.add('hidden');
  loadProjects();
}
window.goHome = goHome;

// ─── Wizard Rendering ───────────────────────────────────
function renderWizard() {
  renderStepIndicator();
  renderStepContent();
}

function renderStepIndicator() {
  const el = document.getElementById('stepIndicator');
  el.innerHTML = APP.steps.map((s, i) => {
    const cls = i < APP.currentStep ? 'done' : i === APP.currentStep ? 'active' : '';
    const check = i < APP.currentStep ? '✓' : (i + 1);
    return `
      <div class="step-item ${cls}">
        ${i > 0 ? '<div class="step-line"></div>' : ''}
        <div class="step-circle">${check}</div>
        <div class="step-label">${s.label}</div>
      </div>`;
  }).join('');
}

function renderStepContent() {
  const step = APP.steps[APP.currentStep];
  const el = document.getElementById('stepContent');

  const renderers = {
    'source': renderSourceStep,
    'stitch': renderStitchStep,
    'review': renderReviewStep,
    'extract_text': renderExtractStep,
    'full_script': renderFullRecapScriptStep,
    'full_review': renderFullRecapReviewStep,
    'full_video': renderFullRecapVideoStep,
    'full_package': renderFullRecapPackageStep,
  };

  const render = renderers[step.id];
  if (render) {
    el.innerHTML = `
      <div class="step-content" id="stepPanel">
        <div class="step-header">
          <div class="step-title">${step.title}</div>
          <div class="step-subtitle">${step.subtitle}</div>
        </div>
        <div id="stepBody"></div>
        <div class="step-actions" id="stepActions"></div>
      </div>`;
    render();
  }
}

// ─── Step: Source ────────────────────────────────────────
// Scraper state kept across re-renders
const SCRAPER = {
  mangaInfo: null,       // result from analyze_url
  analyzing: false,
  downloading: false,
  downloadedPaths: [],   // [{chapter, path, images}]
};

function renderSourceStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div class="settings-panel" style="margin-top:0;">
      <div class="settings-panel-title">📚 Ссылка на мангу или манхву</div>
      <div class="form-group">
        <label class="form-label">URL страницы тайтла</label>
        <div style="display:flex;gap:8px;">
          <input type="text" class="form-input" id="inputMangaUrl" style="flex:1"
                 placeholder="Вставьте ссылку на страницу манги/манхвы"
                 value="${esc(APP._lastUrl || '')}">
          <button class="btn btn-primary" onclick="analyzeUrl()" id="btnAnalyze">Найти главы</button>
        </div>
        <div class="text-xs text-dim mt-2">Приложение проверит доступные главы. После выбора диапазона оно скачает страницы и запустит штатную обработку AniFlow один раз.</div>
      </div>
      <div id="analyzeResult"></div>
    </div>
    <input type="hidden" id="inputProjectName" value="${esc(APP.projectName || '')}">
    <input type="hidden" id="inputSourceFolder" value="${esc(APP.sourceFolder || '')}">`;

  document.getElementById('stepActions').innerHTML = `
    <div class="text-xs text-dim">После скачивания главы приложение продолжит обработку автоматически.</div>`;
  if (SCRAPER.mangaInfo) renderAnalyzeResult(SCRAPER.mangaInfo);
}

async function analyzeUrl() {
  const url = document.getElementById('inputMangaUrl').value.trim();
  if (!url) return toast('Please paste a manhwa URL', 'error');

  APP._lastUrl = url;
  SCRAPER.analyzing = true;
  const btn = document.getElementById('btnAnalyze');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Analyzing...';

  const resultEl = document.getElementById('analyzeResult');
  resultEl.innerHTML = `<div class="text-sm text-dim mt-1"><div class="spinner" style="display:inline-block;vertical-align:middle;margin-right:8px;"></div> Analyzing URL...</div>`;

  try {
    const r = await fetch('/api/scraper/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await r.json();

    if (data.error) {
      resultEl.innerHTML = `<div class="text-sm" style="color:var(--color-error);margin-top:8px;">❌ ${esc(data.error)}</div>`;
      toast(data.error, 'error');
    } else {
      SCRAPER.mangaInfo = data;
      renderAnalyzeResult(data);
      toast(`Found "${data.manga_name}" — ${data.total_chapters} chapters`, 'success');
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="text-sm" style="color:var(--color-error);margin-top:8px;">❌ Network error: ${esc(e.message)}</div>`;
    toast('Analyze failed: ' + e.message, 'error');
  } finally {
    SCRAPER.analyzing = false;
    btn.disabled = false;
    btn.innerHTML = '🔍 Analyze';
  }
}

function renderAnalyzeResult(data) {
  const resultEl = document.getElementById('analyzeResult');
  if (!resultEl) return;

  const chapters = data.chapters || [];
  const firstCh = chapters.length > 0 ? chapters[0].number : 1;
  const lastCh = chapters.length > 0 ? chapters[chapters.length - 1].number : 1;

  resultEl.innerHTML = `
    <div style="margin-top:12px; padding:20px; background:var(--blue-tint); border:2px solid var(--blue); border-radius:var(--radius-md);">
      <div style="display:flex; gap:16px; align-items:flex-start;">
        ${data.cover_url ? `<img src="${esc(data.cover_url)}" style="width:90px; height:125px; border-radius:6px; object-fit:cover; border:2px solid var(--ink); box-shadow: 4px 4px 0 rgba(27,28,31,0.2);" onerror="this.style.display='none'">` : ''}
        <div style="flex:1;">
          <div style="font-size:20px; font-weight:800; font-family:var(--font-display); color:var(--ink); margin-bottom:6px;">📖 ${esc(data.manga_name)}</div>
          <div class="text-xs" style="color:var(--text-secondary); margin-bottom:8px; font-weight:500;">
            <span>🌐 ${esc(data.site || 'Unknown Site')}</span>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
            <div class="badge badge-success" style="font-size:13px; font-weight:600;">✓ ${data.total_chapters} chapters available</div>
            <div class="badge" style="background:var(--paper); border:1px solid var(--blue); color:var(--blue); font-size:13px;">
              📊 Ch.${firstCh} → Ch.${lastCh}
            </div>
          </div>
        </div>
      </div>

      <div style="margin-top:18px;">
        <div class="form-group" style="margin-bottom:10px;">
          <label class="form-label" style="font-size:13px; font-weight:700; color:var(--ink);">📥 Select chapters to download</label>
          <div style="display:flex; gap:8px; align-items:center;">
            <input type="text" class="form-input" id="inputChapterRange" style="flex:1; font-weight:600;"
                   placeholder="e.g. 23 or 23-67 or 1,5,10" value="${Math.round(firstCh)}">
            <button class="btn btn-primary" onclick="downloadChapters()" id="btnDownload" style="font-weight:600; padding:10px 20px;">
              📥 Download
            </button>
          </div>
          <div class="text-xs" style="color:var(--text-secondary); margin-top:6px; line-height:1.5;">
            💡 <b>Single:</b> <code style="background:var(--paper); padding:2px 6px; border-radius:4px; border:1px solid var(--hairline);">23</code>
            <b>Range:</b> <code style="background:var(--paper); padding:2px 6px; border-radius:4px; border:1px solid var(--hairline);">23-67</code>
            <b>Multiple:</b> <code style="background:var(--paper); padding:2px 6px; border-radius:4px; border:1px solid var(--hairline);">1,5,10</code>
            <br>
            <span style="color:var(--text-dim); font-size:11px;">For batch processing: download multiple chapters and process them all at once.</span>
          </div>
        </div>
      </div>

      <!-- Download progress -->
      <div class="progress-container hidden" id="downloadProgress">
        <div class="progress-bar-wrap"><div class="progress-bar-fill" id="downloadProgressBar"></div></div>
        <div class="progress-label">
          <span id="downloadProgressMsg">Downloading...</span>
          <span class="pct" id="downloadProgressPct">0%</span>
        </div>
      </div>

      <div id="downloadResult"></div>
    </div>`;
}

function parseChapterRange(rangeStr, allChapters) {
  const selected = [];
  const parts = rangeStr.split(',').map(s => s.trim());

  for (const part of parts) {
    if (part.includes('-')) {
      const [startStr, endStr] = part.split('-').map(s => s.trim());
      const start = parseFloat(startStr);
      const end = parseFloat(endStr);
      for (const ch of allChapters) {
        if (ch.number >= start && ch.number <= end) {
          selected.push(ch);
        }
      }
    } else {
      const num = parseFloat(part);
      const ch = allChapters.find(c => c.number === num);
      if (ch) selected.push(ch);
    }
  }

  return selected;
}

async function downloadChapters() {
  if (!SCRAPER.mangaInfo) return toast('Analyze a URL first', 'error');

  const rangeStr = document.getElementById('inputChapterRange').value.trim();
  if (!rangeStr) return toast('Enter a chapter number or range', 'error');

  const chapters = parseChapterRange(rangeStr, SCRAPER.mangaInfo.chapters);
  if (chapters.length === 0) return toast('No matching chapters found in that range', 'error');

  const url = document.getElementById('inputMangaUrl').value.trim();
  SCRAPER.downloading = true;

  const btn = document.getElementById('btnDownload');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Downloading...';

  const progressEl = document.getElementById('downloadProgress');
  progressEl.classList.remove('hidden');

  toast(`Downloading ${chapters.length} chapter(s)...`, 'info');

  try {
    const r = await fetch('/api/scraper/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, chapters }),
    });
    const d = await r.json();
    if (d.error) {
      toast(d.error, 'error');
    }
    // Download happens async via websocket — step_complete will fire
  } catch (e) {
    toast('Download failed: ' + e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = '📥 Download';
    SCRAPER.downloading = false;
  }
}

// Listen for download completion
socket.on('step_complete', function _handleDownload(data) {
  if (data.step !== 'download_chapters') return;

  SCRAPER.downloading = false;
  const btn = document.getElementById('btnDownload');
  if (btn) { btn.disabled = false; btn.innerHTML = '📥 Download'; }

  if (data.error) {
    toast('Download error: ' + data.error, 'error');
    return;
  }

  const result = data.result;
  if (!result) return;

  toast(`Downloaded ${result.downloaded?.length || 0} chapter(s) — ${result.total_images || 0} images!`, 'success');

  // Show results and auto-fill project name & path
  const downloaded = result.downloaded || [];
  const resultEl = document.getElementById('downloadResult');
  const mangaName = (result.manga_name || 'Unknown');
  
  if (resultEl && downloaded.length > 0) {
    resultEl.innerHTML = `
      <div style="margin-top:16px; padding:16px; background:var(--green-tint); border:2px solid var(--green); border-radius:8px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
          <div class="badge badge-success" style="font-size:14px; font-weight:700; padding:6px 12px;">✓ Download complete</div>
          <div style="font-size:16px; font-weight:800; font-family:var(--font-display); color:var(--ink);">📚 ${esc(mangaName)}</div>
        </div>
        
        <div style="background:var(--paper); padding:12px; border-radius:6px; border:1px solid var(--green); margin-bottom:12px;">
          <div style="font-size:13px; font-weight:600; color:var(--ink); margin-bottom:8px;">
            📊 Downloaded ${downloaded.length} chapter${downloaded.length > 1 ? 's' : ''} • ${result.total_images || 0} total images
          </div>
          ${downloaded.map(d => `
            <div class="text-xs" style="color:var(--text-secondary); margin:4px 0; padding:4px 8px; background:var(--paper-tint); border-radius:4px; font-family:monospace;">
              📖 Chapter ${String(d.chapter).padStart(5, '0')}: ${d.images} images
              <br><span style="opacity:0.6; font-size:11px;">→ ${esc(d.path)}</span>
            </div>
          `).join('')}
        </div>
        
        ${downloaded.length > 1 ? `
          <div style="padding:12px; background:var(--blue-tint); border:1px solid var(--blue); border-radius:6px; margin-bottom:12px;">
            <div style="font-size:12px; font-weight:700; color:var(--blue); margin-bottom:4px;">🎯 Batch mode is on</div>
            <div style="font-size:11px; color:var(--ink-soft);">
              You downloaded multiple chapters! Use chapter navigation (← →) to switch between them during processing.
            </div>
          </div>
        ` : ''}
      </div>`;

    // Load from the manga root so AniFlow discovers every selected Chapter_XXXXX folder.
    const nameInput = document.getElementById('inputProjectName');
    const folderInput = document.getElementById('inputSourceFolder');
    const mangaRoot = result.download_dir || downloaded[0].path.replace(/[\\/]+Chapter_\\d+$/, '');

    if (nameInput) nameInput.value = mangaName;
    if (folderInput) folderInput.value = mangaRoot;
    APP.projectName = mangaName;
    APP.sourceFolder = mangaRoot;
    SCRAPER.downloadedPaths = downloaded;

    // Downloading the selected range is enough; original AniFlow handles every
    // chapter in the root folder during its existing load/stitch/Crop 2 pipeline.
    startSource();
});

// When user picks a different downloaded chapter from the dropdown
function selectDownloadedChapter(sel) {
  const idx = parseInt(sel.value);
  const paths = SCRAPER.downloadedPaths || [];
  if (!paths[idx]) return;

  const d = paths[idx];
  const mangaName = SCRAPER.mangaInfo?.manga_name || 'Unknown';
  const chNum = String(d.chapter).padStart(3, '0');
  // Project name is just the manhwa title
  const autoName = mangaName;

  const nameInput = document.getElementById('inputProjectName');
  const folderInput = document.getElementById('inputSourceFolder');
  if (nameInput) nameInput.value = autoName;
  if (folderInput) folderInput.value = d.path;

  APP.projectName = autoName;
  APP.sourceFolder = d.path;
}

async function browseFolderForSource() {
  try {
    const response = await fetch('/api/browse-folder', { method: 'POST' });
    const data = await response.json();
    
    if (data.path) {
      document.getElementById('inputSourceFolder').value = data.path;
      APP.sourceFolder = data.path;
      toast('Folder selected: ' + data.path, 'success');
    } else if (data.error) {
      toast('Error: ' + data.error, 'error');
    }
  } catch (error) {
    toast('Failed to open folder browser: ' + error.message, 'error');
  }
}

function collectSourceSettings() {
  return {
    pipeline_mode: 'full_recap',
    video_resolution: '1080p_landscape',
    video_fps: 30,
    video_quality: 'medium',
    animation_style: 'auto',
    full_recap_target_words: 5000,
  };
}

// ─── ⚡ Pipeline settings sync (voices ↔ engine, bg color, pre-fill) ──────
function onBgModeChange(sel) {
  const custom = document.getElementById('bgCustomRow');
  const color = document.getElementById('bgColorRow');
  if (custom) custom.style.display = sel.value === 'custom' ? 'block' : 'none';
  if (color) color.style.display = (sel.value === 'color' || sel.value === 'blur_color') ? 'block' : 'none';
}

function prefillSourceSettings(s) {
  // ✅ SYNC: restore the project's saved settings into the Source form
  if (!s) return;
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el && val !== undefined && val !== null && val !== '') el.value = val;
  };
  set('settingResolution', s.video_resolution);
  set('settingFPS', s.video_fps);
  set('settingAnimation', s.animation_style);
  if (s.bg_mode) {
    const b = document.getElementById('settingBgMode');
    b.value = s.bg_mode;
    onBgModeChange(b);
  }
  set('settingBgColor', s.bg_color);
  if (s.color_opacity !== undefined && s.color_opacity !== null) {
    const pct = Math.round(s.color_opacity * 100);
    set('settingBgOpacity', pct);
    const v = document.getElementById('bgOpacityVal');
    if (v) v.textContent = pct + '%';
  }
  set('settingQuality', s.video_quality);
  set('settingCustomBg', s.custom_bg_path);
  set('settingWatermark', s.watermark_path);
  if (typeof s.fast_mode === 'boolean') {
    const cb = document.getElementById('settingSpeedMode');
    if (cb) { cb.checked = s.fast_mode; toggleSpeedOptions(cb); }
  }
  if (s.fast_mode) setSpeedSettings(s);
}

function browseFileFor(targetId) {
  fetch('/api/browse-file', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.path) {
        const el = document.getElementById(targetId);
        if (el) el.value = data.path;
      } else if (data.error) {
        toast(data.error, 'error');
      }
    })
    .catch(e => toast('File browser failed: ' + e.message, 'error'));
}

async function startSource() {
  const name = document.getElementById('inputProjectName').value.trim();
  const folder = document.getElementById('inputSourceFolder').value.trim();

  if (!name) return toast('Project name is required', 'error');
  if (!folder) return toast('Source folder or archive file path is required', 'error');

  APP.projectName = name;
  APP.sourceFolder = folder;
  APP.settings = collectSourceSettings();
  localStorage.setItem('speedPanelTouched', 'true');

  // Load images
  setRunning(true, 'Loading images...');
  try {
    const r = await fetch('/api/run/step/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: name, source_folder: folder, settings: APP.settings }),
    });
    const d = await r.json();
    if (d.error) { toast(d.error, 'error'); setRunning(false); return; }
    toast('Chapter loaded!', 'success');
  } catch (e) {
    toast('Failed to load: ' + e.message, 'error');
    setRunning(false);
  }
}

// ─── Step: Stitch & Detect ──────────────────────────────
let drawMode = false; // Track if we're in draw mode

function renderStitchStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>
    
    <p class="text-sm text-dim mb-1">Stitch pages into long strips, then detect and crop individual panels. You can manually adjust detection boxes.</p>

    <div class="zoom-controls" id="stitchZoomBar" style="display:none">
      <button class="btn btn-ghost" onclick="stitchZoom(-20)">−</button>
      <span class="zoom-label" id="stitchZoomLabel">100%</span>
      <button class="btn btn-ghost" onclick="stitchZoom(20)">+</button>
      <button class="btn btn-ghost" onclick="stitchZoomReset()">Reset</button>
      <button class="btn btn-ghost" id="btnDrawMode" onclick="toggleDrawMode()" title="Enable/Disable drawing new boxes" style="margin-left:16px; font-size:14px;">✏️ Draw</button>
      <span class="text-xs text-dim" style="margin-left:8px" id="stitchImgInfo"></span>
      <span id="drawModeHint" class="text-xs" style="display:none; margin-left:12px; color: var(--red); font-weight: 600;">✏️ Draw mode is on — click and drag to add boxes</span>
    </div>

    <div class="stitched-viewer" id="stitchViewer" style="display:none">
      <div class="stitched-inner" id="stitchInner">
        <div id="stitchImgList" style="position: relative;">
          <!-- Images go here -->
          <div class="stitched-overlay" id="stitchOverlay"></div>
        </div>
      </div>
    </div>

    <div class="progress-container hidden" id="stitchProgress">
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="stitchProgressBar"></div></div>
      <div class="progress-label">
        <span id="stitchProgressMsg">Processing...</span>
        <span class="pct" id="stitchProgressPct">0%</span>
      </div>
    </div>

    <div id="stitchBoxCount" class="text-xs text-dim mt-1"></div>`;

  const isNarrated = APP.mode === 'narrated' || APP.mode === 'full_recap';
  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">

      <button class="btn btn-secondary" onclick="runStitch()" id="btnStitch">Stitch Pages</button>
      <button class="btn btn-secondary" onclick="runDetect()" id="btnDetect" disabled>${isNarrated ? 'Detect 1 — Bubble Panels' : 'Detect Panels'}</button>
      <button class="btn btn-secondary" onclick="removeOverlappingBoxes()" id="btnRemoveOverlaps" style="display:none" title="Auto-fix overlapping boxes">🔧 Fix Overlaps</button>
      <button class="btn btn-secondary" onclick="saveStitchBoxes()" id="btnSaveBoxes" style="display:none">💾 Save Boxes</button>
      <button class="btn btn-secondary" onclick="runCrop()" id="btnCrop" disabled>${isNarrated ? 'Crop 1 — Bubble Panels' : 'Crop Panels'}</button>
      ${isNarrated ? `
      <button class="btn btn-secondary" onclick="runStitch2()" id="btnStitch2" disabled>Stitch 2 — Combine</button>
      <button class="btn btn-secondary" onclick="runDetect2()" id="btnDetect2" disabled>Detect 2 — Art Panels</button>
      <button class="btn btn-secondary" onclick="runCrop2()" id="btnCrop2" disabled>Crop 2 — Art Panels</button>` : ''}
      <button class="btn btn-primary" onclick="nextStep()" id="btnStitchNext" disabled>Continue →</button>
    </div>`;

  // Check existing state and load preview
  loadProjectData(APP.projectName).then(() => {
    if (APP.projectData) {
      const stage = APP.projectData.stage;
      const STAGES = ['init','loaded','stitched','detected1','cropped1','stitched2','detected2','cropped2','text_extracted','text_removed','narrated','audio_done','video_done'];
      const idx = STAGES.indexOf(stage);
      if (idx >= 2) { enable('btnDetect'); loadStitchedPreview(); }
      if (idx >= 3) { enable('btnCrop'); loadStitchedPreview(); }
      if (isNarrated) {
        // ✅ Two-stage flow: Stitch2 → Detect2 → Crop2
        if (idx >= 4) { enable('btnStitch2'); }
        if (idx >= 5) { enable('btnDetect2'); loadStitched2Preview(); }
        if (idx >= 6) { enable('btnCrop2'); }
        if (idx >= 7) { enable('btnStitchNext'); }
      } else {
        if (idx >= 4) { enable('btnStitchNext'); }
      }
    }
  });
}

// ─── Stitch: Stitched Image Viewer + Box Editor ────────────
let stitchZoomLevel = 100;
let stitchNatW = 1, stitchNatH = 1;
let stitchBoxes = [];
let stitchAction = null;
let stitchStartEv = null;
let stitchStartBox = null;

function stitchZoom(delta) {
  stitchZoomLevel = Math.max(20, Math.min(500, stitchZoomLevel + delta));
  const inner = document.getElementById('stitchInner');
  const label = document.getElementById('stitchZoomLabel');
  if (inner) inner.style.width = stitchZoomLevel + '%';
  if (label) label.textContent = stitchZoomLevel + '%';
}
function stitchZoomReset() { stitchZoomLevel = 100; stitchZoom(0); }

// View Stitched Image 2 (the re-stitched bubble panels) with its Detect 2 boxes
function loadStitched2Preview() {
  APP.stitchViewTarget = 2;
  stitchBoxes = [];
  return loadStitchedPreview();
}
window.loadStitched2Preview = loadStitched2Preview;

async function loadStitchedPreview() {
  try {
    const useStitch2 = APP.stitchViewTarget === 2;
    const r = await fetch(useStitch2
      ? `/api/stitched-image-2/${encodeURIComponent(APP.projectName)}`
      : `/api/stitched-image/${encodeURIComponent(APP.projectName)}`);
    const data = await r.json();
    if (!data.parts || data.parts.length === 0) return;

    // Image URLs are mtime-versioned by the backend, so the browser caches
    // them across chapter switches and re-stitching busts the cache naturally
    const parts = data.parts;

    document.getElementById('stitchViewer').style.display = '';
    document.getElementById('stitchZoomBar').style.display = '';

    const imgList = document.getElementById('stitchImgList');
    const overlay = document.getElementById('stitchOverlay');
    
    // Clear only the images, preserve the overlay
    Array.from(imgList.children).forEach(child => {
      if (child !== overlay) {
        imgList.removeChild(child);
      }
    });

    let loadedCount = 0, totalH = 0, firstW = 0;

    parts.forEach(partUrl => {
      const el = document.createElement('img');
      el.src = partUrl;
      el.style.width = '100%';
      el.style.display = 'block';
      el.onload = () => {
        if (firstW === 0) firstW = el.naturalWidth;
        totalH += el.naturalHeight;
        loadedCount++;
        if (loadedCount === data.parts.length) {
          stitchNatW = firstW;
          stitchNatH = totalH;
          
          document.getElementById('stitchImgInfo').textContent = `${stitchNatW} × ${stitchNatH}px`;

          // Load boxes from project state — per viewer target
          const boxes = APP.stitchViewTarget === 2
            ? (APP.projectData?.stitched_boxes_2 || [])
            : (APP.projectData?.stitched_boxes_1 || APP.projectData?.stitched_boxes || []);
          if (boxes.length > 0) {
            stitchBoxes = boxes.map(b => ({...b}));
            
            // Auto-remove overlaps after loading
            const removed = removeOverlappingBoxes(true);
            if (removed > 0) {
              toast(`Auto-removed ${removed} overlapping box${removed > 1 ? 'es' : ''} from detection`, 'info');
            }
            
            renderStitchBoxes();
          }
        }
      };
      // Insert images before the overlay
      imgList.insertBefore(el, overlay);
    });
  } catch (e) { console.error('loadStitchedPreview error:', e); }
}

function toggleDrawMode() {
  drawMode = !drawMode;
  const btn = document.getElementById('btnDrawMode');
  const hint = document.getElementById('drawModeHint');
  const overlay = document.getElementById('stitchOverlay');
  
  if (drawMode) {
    btn.classList.add('active');
    btn.style.background = 'var(--red)';
    btn.style.color = '#fff';
    hint.style.display = 'inline';
    overlay.classList.add('draw-mode');
    toast('✏️ Draw Mode: Click and drag on the image to add new boxes', 'info');
  } else {
    btn.classList.remove('active');
    btn.style.background = '';
    btn.style.color = '';
    hint.style.display = 'none';
    overlay.classList.remove('draw-mode');
  }
}

function renderStitchBoxes() {
  const overlay = document.getElementById('stitchOverlay');
  overlay.style.display = 'block';
  overlay.classList.add('interactive');
  overlay.innerHTML = '';
  // Only allow drawing when draw mode is enabled
  overlay.onmousedown = (e) => { if (e.target === overlay && drawMode) startStitchDraw(e); };

  // Sort boxes by vertical position (top-to-bottom) so numbering is sequential
  // Skip sorting during active draw/drag/resize to avoid corrupting indices
  if (!stitchAction) {
    stitchBoxes.sort((a, b) => a.y - b.y);
  }

  document.getElementById('stitchBoxCount').textContent = `${stitchBoxes.length} detection boxes`;
  document.getElementById('stitchBoxCount').title = 'Click ✏️ Draw to add new boxes. Drag boxes to move them. Use corner/edge handles to resize. Click ✕ to delete.';
  
  // Check for overlaps and update message
  let overlapCount = 0;
  for (let i = 0; i < stitchBoxes.length; i++) {
    for (let j = i + 1; j < stitchBoxes.length; j++) {
      if (boxIoU(stitchBoxes[i], stitchBoxes[j]) > 0.30) {
        overlapCount++;
      }
    }
  }
  
  if (overlapCount > 0) {
    document.getElementById('stitchBoxCount').innerHTML = `${stitchBoxes.length} detection boxes <span style="color: var(--amber); font-weight: 600;">⚠️ ${overlapCount} overlap${overlapCount > 1 ? 's' : ''} detected</span>`;
  }
  
  const hasBoxes = stitchBoxes.length > 0;
  document.getElementById('btnSaveBoxes').style.display = hasBoxes ? '' : 'none';
  const overlapBtn = document.getElementById('btnRemoveOverlaps');
  if (overlapBtn) overlapBtn.style.display = hasBoxes ? '' : 'none';

  stitchBoxes.forEach((box, idx) => {
    const bx = (box.x / stitchNatW * 100);
    const by = (box.y / stitchNatH * 100);
    const bw = (box.w / stitchNatW * 100);
    const bh = (box.h / stitchNatH * 100);

    // Check if this box overlaps with any other box
    let hasOverlap = false;
    for (let j = 0; j < stitchBoxes.length; j++) {
      if (j !== idx) {
        const iou = boxIoU(box, stitchBoxes[j]);
        if (iou > 0.30) {
          hasOverlap = true;
          break;
        }
      }
    }

    const b = document.createElement('div');
    b.className = hasOverlap ? 'detect-box overlapping' : 'detect-box';
    b.style.cssText = `left:${bx}%;top:${by}%;width:${bw}%;height:${bh}%`;
    b.dataset.idx = idx;
    b.title = hasOverlap 
      ? `Panel #${idx + 1} - ⚠️ OVERLAPPING - Drag to move, resize with handles, click ✕ to delete`
      : `Panel #${idx + 1} - Drag to move, resize with handles, click ✕ to delete`;

    // Label
    const lbl = document.createElement('div');
    lbl.className = 'box-label';
    lbl.textContent = hasOverlap ? `#${idx + 1} ⚠️` : `#${idx + 1}`;
    b.appendChild(lbl);

    // Close button
    const cls = document.createElement('button');
    cls.className = 'close-btn';
    cls.textContent = '✕';
    cls.onclick = (e) => { e.stopPropagation(); stitchBoxes.splice(idx, 1); renderStitchBoxes(); };
    b.appendChild(cls);

    // Resize handles
    ['nw','ne','sw','se','n','s','e','w'].forEach(dir => {
      const h = document.createElement('div');
      h.className = `resize-handle ${dir}`;
      h.onmousedown = (e) => startStitchResize(e, idx, dir);
      b.appendChild(h);
    });

    b.onmousedown = (e) => {
      if (e.target.classList.contains('resize-handle') || e.target.classList.contains('close-btn')) return;
      startStitchDrag(e, idx);
    };

    overlay.appendChild(b);
  });
}

function startStitchDraw(e) {
  e.preventDefault();
  const overlay = document.getElementById('stitchOverlay');
  const rect = overlay.getBoundingClientRect();
  const sx = stitchNatW / rect.width, sy = stitchNatH / rect.height;
  const startX = (e.clientX - rect.left) * sx;
  const startY = (e.clientY - rect.top) * sy;
  const newIdx = stitchBoxes.length;
  stitchBoxes.push({ x: startX, y: startY, w: 10, h: 10 });
  stitchAction = { type: 'draw', idx: newIdx, startX, startY };
  document.addEventListener('mousemove', onStitchMouseMove);
  document.addEventListener('mouseup', onStitchMouseUp);
  renderStitchBoxes();
}

function startStitchDrag(e, idx) {
  e.preventDefault();
  stitchAction = { type: 'drag', idx };
  stitchStartEv = { x: e.clientX, y: e.clientY };
  stitchStartBox = { ...stitchBoxes[idx] };
  document.addEventListener('mousemove', onStitchMouseMove);
  document.addEventListener('mouseup', onStitchMouseUp);
}

function startStitchResize(e, idx, dir) {
  e.preventDefault(); e.stopPropagation();
  stitchAction = { type: 'resize', idx, dir };
  stitchStartEv = { x: e.clientX, y: e.clientY };
  stitchStartBox = { ...stitchBoxes[idx] };
  document.addEventListener('mousemove', onStitchMouseMove);
  document.addEventListener('mouseup', onStitchMouseUp);
}

function onStitchMouseMove(e) {
  if (!stitchAction) return;
  const overlay = document.getElementById('stitchOverlay');
  const rect = overlay.getBoundingClientRect();
  const sx = stitchNatW / rect.width, sy = stitchNatH / rect.height;
  const box = stitchBoxes[stitchAction.idx];

  if (stitchAction.type === 'draw') {
    const curX = (e.clientX - rect.left) * sx;
    const curY = (e.clientY - rect.top) * sy;
    box.x = Math.max(0, Math.min(stitchAction.startX, curX));
    box.y = Math.max(0, Math.min(stitchAction.startY, curY));
    box.w = Math.min(Math.abs(curX - stitchAction.startX), stitchNatW - box.x);
    box.h = Math.min(Math.abs(curY - stitchAction.startY), stitchNatH - box.y);
  } else {
    const dx = (e.clientX - stitchStartEv.x) * sx;
    const dy = (e.clientY - stitchStartEv.y) * sy;

    if (stitchAction.type === 'drag') {
      box.x = Math.max(0, Math.min(stitchStartBox.x + dx, stitchNatW - box.w));
      box.y = Math.max(0, Math.min(stitchStartBox.y + dy, stitchNatH - box.h));
    } else if (stitchAction.type === 'resize') {
      const dir = stitchAction.dir;
      if (dir.includes('n')) { let ny = Math.max(0, stitchStartBox.y + dy), nh = stitchStartBox.h + (stitchStartBox.y - ny); if (nh > 10) { box.y = ny; box.h = nh; } }
      if (dir.includes('s')) { let nh = Math.min(stitchStartBox.h + dy, stitchNatH - stitchStartBox.y); if (nh > 10) box.h = nh; }
      if (dir.includes('w')) { let nx = Math.max(0, stitchStartBox.x + dx), nw = stitchStartBox.w + (stitchStartBox.x - nx); if (nw > 10) { box.x = nx; box.w = nw; } }
      if (dir.includes('e')) { let nw = Math.min(stitchStartBox.w + dx, stitchNatW - stitchStartBox.x); if (nw > 10) box.w = nw; }
    }
  }
  renderStitchBoxes();
}

function onStitchMouseUp() {
  const wasDrawing = stitchAction && stitchAction.type === 'draw';
  stitchAction = null;
  document.removeEventListener('mousemove', onStitchMouseMove);
  document.removeEventListener('mouseup', onStitchMouseUp);
  // After drawing or dragging, re-sort and re-render so numbering stays sequential
  if (wasDrawing) renderStitchBoxes();
}

async function saveStitchBoxes() {
  if (stitchBoxes.length === 0) {
    toast('No boxes to save', 'info');
    return;
  }
  // Ensure boxes are in top-to-bottom reading order before saving
  stitchBoxes.sort((a, b) => a.y - b.y);
  // ✅ Two-stage: save to boxes2 when editing the Stitched Image 2 viewer
  const endpoint = APP.stitchViewTarget === 2 ? 'boxes2' : 'boxes';
  try {
    await fetch(`/api/projects/${encodeURIComponent(APP.projectName)}/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boxes: stitchBoxes }),
    });
    toast(`✅ Saved ${stitchBoxes.length} detection boxes - These will be used when you click "Crop Panels"`, 'success');
  } catch (e) { toast('Failed to save boxes: ' + e.message, 'error'); }
}

function removeOverlappingBoxes(auto = false) {
  if (stitchBoxes.length === 0) {
    if (!auto) toast('No boxes to check', 'info');
    return 0;
  }
  
  // IoU-based Non-Maximum Suppression — remove smaller box when overlap > threshold
  const IOU_THRESHOLD = 0.30;
  const before = stitchBoxes.length;

  // Sort boxes by area (largest first) for NMS — renderStitchBoxes will re-sort by Y position
  stitchBoxes.sort((a, b) => (b.w * b.h) - (a.w * a.h));

  const keep = [];
  const removed = new Set();

  for (let i = 0; i < stitchBoxes.length; i++) {
    if (removed.has(i)) continue;
    keep.push(stitchBoxes[i]);

    for (let j = i + 1; j < stitchBoxes.length; j++) {
      if (removed.has(j)) continue;
      const iou = boxIoU(stitchBoxes[i], stitchBoxes[j]);
      if (iou > IOU_THRESHOLD) {
        removed.add(j); // Remove the smaller overlapping box
      }
    }
  }

  stitchBoxes = keep;
  const after = stitchBoxes.length;
  const diff = before - after;

  if (!auto) {
    if (diff > 0) {
      toast(`Removed ${diff} overlapping box${diff > 1 ? 'es' : ''} (${after} remaining)`, 'success');
    } else {
      toast('No overlapping boxes found', 'info');
    }
    renderStitchBoxes();
  }
  
  return diff;
}

function boxIoU(a, b) {
  // Compute Intersection over Union for two {x, y, w, h} boxes
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.w, b.x + b.w);
  const y2 = Math.min(a.y + a.h, b.y + b.h);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  if (inter === 0) return 0;
  const areaA = a.w * a.h;
  const areaB = b.w * b.h;
  return inter / (areaA + areaB - inter);
}

function isPipelineBusy() {
  // Guard against double-clicking run buttons while a step is running —
  // overlapping steps corrupt per-chapter state
  if (APP.running) {
    toast('Please wait — a step is already running. Watch the progress bar.', 'warning');
    return true;
  }
  return false;
}

// ─── 🚀 Full Batch Pipeline (one-click) ──────────────────
const BATCH_STEP_LABELS = {
  load: 'Loading images',
  stitch: 'Stitching pages',
  detect1: 'Detecting bubble panels',
  crop1: 'Cropping bubble panels',
  stitch2: 'Stitching bubble panels',
  detect2: 'Detecting art panels',
  crop2: 'Cropping art panels',
  extract_dialogue: 'Extracting text',
  remove_text: 'Cleaning panels',
  narrate_mapped: 'Writing narration',
  audio: 'Generating audio',
  video: 'Generating clips',
};

function _batchStepsForMode() {
  // Narrated mode: full two-stage flow — bubble panels (Detect/Crop 1) feed
  // text extraction, art panels (Stitch 2 → Detect 2 → Crop 2) feed narration
  // and the final video. No remove_text: Crop 2 already yields clean panels.
  return APP.mode === 'narrated'
    ? ['stitch', 'detect1', 'crop1', 'stitch2', 'detect2', 'crop2',
       'extract_dialogue', 'narrate_mapped', 'audio', 'video']
    : ['stitch', 'detect1', 'crop1', 'extract_dialogue', 'audio', 'video'];
}

function openWizardAtStep(projectName, stepId) {
  // Open the pipeline wizard on a specific step (used after full batch → Review Clips)
  APP.mode = 'full_recap';
  APP.steps = FULL_RECAP_STEPS;
  APP.projectName = projectName;
  document.getElementById('viewHome').classList.add('hidden');
  document.getElementById('viewWizard').classList.remove('hidden');
  const idx = APP.steps.findIndex(s => s.id === stepId);
  APP.currentStep = idx >= 0 ? idx : 1;
  renderWizard();
  loadProjectData(projectName).then(() => {
    updateChapterNavUI();
    renderWizard(); // re-render with fresh project data (stage-aware buttons)
  });
}

async function _startFullBatch(payload) {
  if (isPipelineBusy()) return;
  try {
    const r = await fetch('/api/run/full-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!r.ok) {
      toast(`Could not start batch: ${data.error}`, 'error');
      return false;
    }
    APP.batchRunning = true;
    APP.mode = 'full_recap';
    APP.steps = FULL_RECAP_STEPS;
    APP.projectName = payload.project_name;
    showBatchOverlay(payload.project_name, payload.steps || _batchStepsForMode());
    // Jump to the stitch step so the user sees live context
    if (APP.mode && APP.steps) {
      APP.currentStep = 1;
      renderWizard();
    }
    return true;
  } catch (e) {
    toast('Failed to start batch: ' + e.message, 'error');
    return false;
  }
}

async function runFullBatchFromSource() {
  const name = document.getElementById('inputProjectName').value.trim();
  const folder = document.getElementById('inputSourceFolder').value.trim();
  if (!name) return toast('Project name is required', 'error');
  if (!folder) return toast('Folder path is required', 'error');
  APP.projectName = name;
  APP.sourceFolder = folder;
  APP.settings = collectSourceSettings();
  localStorage.setItem('speedPanelTouched', 'true');
  await _startFullBatch({
    project_name: name,
    source_folder: folder,
    settings: APP.settings,
    steps: _batchStepsForMode(),
  });
}

async function runFullBatchForProject(projectName) {
  // Resume an existing project (dashboard / stitch step) with its saved settings
  APP.projectName = projectName;
  APP.mode = 'full_recap';
  APP.steps = FULL_RECAP_STEPS;
  let settings = {};
  try {
    const r = await fetch(`/api/projects/${encodeURIComponent(projectName)}`);
    if (r.ok) settings = (await r.json()).settings || {};
  } catch (e) { /* fall back to empty settings */ }
  await _startFullBatch({
    project_name: projectName,
    settings: settings,
    steps: _batchStepsForMode(),
  });
}

function showBatchOverlay(project, steps) {
  hideBatchOverlay();
  const stepList = (steps || []).map((s, i) =>
    `<span id="batchStepChip_${s}" style="padding:3px 10px; border-radius:4px; font-size:11px; border:1px solid var(--hairline); background:var(--desk); color:var(--text-dim);">${BATCH_STEP_LABELS[s] || s}</span>`
  ).join(' ');
  const el = document.createElement('div');
  el.id = 'batchOverlay';
  el.style.cssText = 'position:fixed; inset:0; background:rgba(27,28,31,0.55); z-index:9999; display:flex; align-items:center; justify-content:center;';
  el.innerHTML = `
    <div style="width:min(720px, 92vw); background:var(--paper); border:2px solid var(--ink); border-radius:8px; box-shadow:8px 8px 0 rgba(27,28,31,0.25); padding:28px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
        <div style="font-size:18px; font-weight:800; font-family:var(--font-display);">🚀 Full Batch Running</div>
        <button class="btn btn-secondary" style="padding:6px 14px;" onclick="cancelFullBatch()">✕ Cancel</button>
      </div>
      <div style="font-size:13px; color:var(--text-secondary); margin-bottom:12px;">${esc(project)}</div>
      <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:18px;">${stepList}</div>
      <div id="batchOverlayStatus" style="font-size:15px; font-weight:700; margin-bottom:6px;">Starting…</div>
      <div id="batchOverlayMsg" style="font-size:12px; color:var(--text-dim); margin-bottom:14px; min-height:16px;"></div>
      <div style="background:var(--desk); border:2px solid var(--ink); border-radius:999px; height:14px; overflow:hidden;">
        <div id="batchOverlayBar" style="height:100%; width:0%; background:var(--blue); transition:width 0.3s;"></div>
      </div>
      <div id="batchOverlayPercent" style="text-align:right; font-size:12px; color:var(--text-dim); margin-top:6px;">0%</div>
    </div>`;
  document.body.appendChild(el);
}

function updateBatchOverlay(step, message, percent) {
  const statusEl = document.getElementById('batchOverlayStatus');
  const msgEl = document.getElementById('batchOverlayMsg');
  const barEl = document.getElementById('batchOverlayBar');
  const pctEl = document.getElementById('batchOverlayPercent');
  if (step) {
    if (statusEl) statusEl.textContent = BATCH_STEP_LABELS[step] || step;
    document.querySelectorAll('[id^="batchStepChip_"]').forEach(c => {
      c.style.background = 'var(--desk)';
      c.style.color = 'var(--text-dim)';
      c.style.borderColor = 'var(--hairline)';
    });
    const chip = document.getElementById(`batchStepChip_${step}`);
    if (chip) { chip.style.background = 'var(--blue)'; chip.style.color = '#fff'; chip.style.borderColor = 'var(--ink)'; }
  }
  if (msgEl && message) msgEl.textContent = message;
  const pct = Math.max(0, Math.min(100, Math.round(percent || 0)));
  if (barEl) barEl.style.width = pct + '%';
  if (pctEl) pctEl.textContent = pct + '%';
}

function hideBatchOverlay() {
  const el = document.getElementById('batchOverlay');
  if (el) el.remove();
}

async function cancelFullBatch() {
  try { await fetch('/api/cancel', { method: 'POST' }); } catch (e) { /* ignore */ }
  const statusEl = document.getElementById('batchOverlayStatus');
  if (statusEl) statusEl.textContent = 'Cancelling — finishing current item…';
}

function playDoneBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1108.7, 1318.5].forEach((f, i) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f; o.type = 'sine';
      const t0 = ctx.currentTime + i * 0.18;
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(0.25, t0 + 0.03);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.55);
      o.connect(g); g.connect(ctx.destination);
      o.start(t0); o.stop(t0 + 0.6);
    });
  } catch (e) { /* audio not available */ }
}


const SPEED_BUILTINS = {
  'builtin:low':      { clip_workers: 2, encoder: 'libx264',      edge_workers: 3, elevenlabs_workers: 1, kokoro_gpu: false },
  'builtin:balanced': { clip_workers: 4, encoder: 'auto',         edge_workers: 6, elevenlabs_workers: 2, kokoro_gpu: true  },
  'builtin:high':     { clip_workers: 8, encoder: 'videotoolbox', edge_workers: 8, elevenlabs_workers: 2, kokoro_gpu: true  },
};

let _speedHardware = null; // cached /api/hardware response

function _getSavedSpeedPresets() {
  try { return JSON.parse(localStorage.getItem('speedPresets') || '{}'); }
  catch (e) { return {}; }
}

function getSpeedSettings() {
  const num = (id, lo, hi, dflt) => {
    const el = document.getElementById(id);
    if (!el) return dflt;
    const v = parseInt(el.value, 10);
    return isNaN(v) ? dflt : Math.max(lo, Math.min(hi, v));
  };
  const kEl = document.getElementById('speedKokoroGPU');
  return {
    clip_workers: num('speedClipWorkers', 1, 16, 4),
    encoder: (document.getElementById('speedEncoder') || {}).value || 'auto',
    edge_workers: num('speedEdgeWorkers', 1, 12, 6),
    elevenlabs_workers: num('speedELWorkers', 1, 4, 2),
    kokoro_gpu: kEl ? kEl.checked : true,
  };
}

function setSpeedSettings(s) {
  const setNum = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  setNum('speedClipWorkers', s.clip_workers);
  const enc = document.getElementById('speedEncoder'); if (enc) enc.value = s.encoder;
  setNum('speedEdgeWorkers', s.edge_workers);
  setNum('speedELWorkers', s.elevenlabs_workers);
  const kEl = document.getElementById('speedKokoroGPU'); if (kEl) kEl.checked = !!s.kokoro_gpu;
}

function refreshSpeedPresetSelect(selected) {
  const sel = document.getElementById('speedPresetSelect');
  if (!sel) return;
  const saved = _getSavedSpeedPresets();
  // Keep built-ins, drop old custom entries, re-add saved ones
  Array.from(sel.options).forEach(o => { if (o.value && !o.value.startsWith('builtin:') && o.value !== 'custom') o.remove(); });
  Object.keys(saved).sort().forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = '⭐ ' + name;
    sel.appendChild(opt);
  });
  sel.value = selected || 'custom';
}

function applySpeedPreset(value) {
  const s = SPEED_BUILTINS[value] || _getSavedSpeedPresets()[value];
  if (s) { setSpeedSettings(s); }
  const sel = document.getElementById('speedPresetSelect');
  if (sel && sel.value !== value) sel.value = value;
}

function saveSpeedPreset() {
  const nameEl = document.getElementById('speedPresetName');
  const name = (nameEl.value || '').trim();
  if (!name) { toast('Enter a preset name first', 'warning'); return; }
  const presets = _getSavedSpeedPresets();
  presets[name] = getSpeedSettings();
  localStorage.setItem('speedPresets', JSON.stringify(presets));
  refreshSpeedPresetSelect(name);
  toast(`Preset "${name}" saved`, 'success');
}

function deleteSpeedPreset() {
  const sel = document.getElementById('speedPresetSelect');
  const value = sel ? sel.value : '';
  if (!value || value === 'custom' || value.startsWith('builtin:')) {
    toast('Select a saved (⭐) preset to delete', 'warning');
    return;
  }
  const presets = _getSavedSpeedPresets();
  delete presets[value];
  localStorage.setItem('speedPresets', JSON.stringify(presets));
  refreshSpeedPresetSelect('custom');
  toast(`Preset "${value}" deleted`, 'info');
}

function resetSpeedDefaults() {
  applySpeedPreset('builtin:balanced');
  toast('Speed settings reset to Balanced', 'info');
}

async function initSpeedPanel() {
  // Fill smart defaults from the actual machine (once per session)
  const enc = document.getElementById('speedEncoder');
  if (!_speedHardware && enc) {
    try {
      const r = await fetch('/api/hardware');
      _speedHardware = await r.json();
    } catch (e) { _speedHardware = { cpu_count: 4, platform: '?', videotoolbox: false }; }
    if (enc) {
      const vtOpt = enc.querySelector('option[value="videotoolbox"]');
      if (vtOpt && !_speedHardware.videotoolbox) {
        vtOpt.disabled = true;
        vtOpt.textContent = 'Hardware (not available on this system)';
      }
    }
    const hint = document.getElementById('speedEncoderHint');
    if (hint) {
      hint.textContent = _speedHardware.videotoolbox
        ? `Auto — detected ${_speedHardware.cpu_count} CPU cores + hardware encoder`
        : `Auto — detected ${_speedHardware.cpu_count} CPU cores, no hardware encoder`;
    }
    // If no saved custom values exist yet, suggest cpu-based clip workers
    const cw = document.getElementById('speedClipWorkers');
    if (cw && !localStorage.getItem('speedPanelTouched')) {
      cw.value = Math.max(2, Math.min(8, (_speedHardware.cpu_count || 4) - 2));
    }
  }
  refreshSpeedPresetSelect('custom');
}

function toggleSpeedOptions(cb) {
  const panel = document.getElementById('speedOptionsPanel');
  if (panel) panel.style.display = cb.checked ? 'block' : 'none';
  if (cb.checked) initSpeedPanel();
  onSpeedModeToggle(cb);
}

function onSpeedModeToggle(cb) {
  // Remember the choice so it survives page reloads
  localStorage.setItem('speedMode', cb.checked ? 'true' : 'false');
  toast(cb.checked ? '⚡ Speed Mode enabled — hardware encoder + parallel TTS/clips' : 'Speed Mode disabled — classic mode', 'info');

  // If a project is already open, sync the setting into its saved state so
  // the next audio/video step picks it up immediately
  if (APP.projectName) {
    fetch(`/api/projects/${encodeURIComponent(APP.projectName)}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fast_mode: cb.checked, ...getSpeedSettings() }),
    }).catch(e => console.error('Speed Mode sync failed:', e));
  }
}


async function runStitch() {
  if (isPipelineBusy()) return;
  setRunning(true, 'Stitching pages...');
  showProgress('stitch');
  try {
    await fetch('/api/run/step/stitch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
  } catch (e) { toast('Stitch failed: ' + e.message, 'error'); setRunning(false); }
}

async function runDetect() {
  if (isPipelineBusy()) return;
  setRunning(true, 'Detecting panels...');
  showProgress('stitch');
  try {
    await fetch('/api/run/step/detect1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
    // Detect 1 edits boxes on Stitched Image 1 — switch viewer back
    APP.stitchViewTarget = 1;
  } catch (e) { toast('Detect failed: ' + e.message, 'error'); setRunning(false); }
}

// ── ✅ Two-stage (Narrated mode): Stitch 2 → Detect 2 → Crop 2 ──
async function runStitch2() {
  if (isPipelineBusy()) return;
  setRunning(true, 'Stitching bubble panels...');
  showProgress('stitch');
  try {
    await fetch('/api/run/step/stitch2', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
  } catch (e) { toast('Stitch 2 failed: ' + e.message, 'error'); setRunning(false); }
}

async function runDetect2() {
  if (isPipelineBusy()) return;
  setRunning(true, 'Detecting art panels...');
  showProgress('stitch');
  try {
    await fetch('/api/run/step/detect2', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
    // Switch the viewer to Stitched Image 2 so art-panel boxes are visible
    APP.stitchViewTarget = 2;
    stitchBoxes = [];
    loadStitchedPreview();
  } catch (e) { toast('Detect 2 failed: ' + e.message, 'error'); setRunning(false); }
}

async function runCrop2() {
  if (isPipelineBusy()) return;
  setRunning(true, 'Cropping art panels...');
  showProgress('stitch');
  try {
    await fetch('/api/run/step/crop2', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
  } catch (e) { toast('Crop 2 failed: ' + e.message, 'error'); setRunning(false); }
}

async function runCrop() {
  if (isPipelineBusy()) return;
  if (stitchBoxes.length === 0) {
    toast('No boxes to crop. Run "Detect Panels" first or draw boxes manually.', 'warning');
    return;
  }
  setRunning(true, `Cropping ${stitchBoxes.length} panels...`);
  showProgress('stitch');
  try {
    await fetch('/api/run/step/crop1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
  } catch (e) { toast('Crop failed: ' + e.message, 'error'); setRunning(false); }
}

// ─── Step: Review ───────────────────────────────────────
function renderReviewStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>
    
    <p class="text-sm text-dim mb-1">Review cropped panels. Delete junk panels or crop unwanted content (e.g. "To be continued" sections).</p>
    <div id="panelReviewGrid" style="margin-top: 20px;">
      <div class="empty-state">
        <div class="spinner spinner-lg" style="margin:0 auto 12px"></div>
        <div class="empty-state-text">Loading panels...</div>
      </div>
    </div>
    <div id="panelCount" class="text-xs text-dim mt-1"></div>`;

  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-primary" onclick="nextStep()">Looks Good, Continue →</button>
    </div>`;

  loadPanelReview();
}
window.loadPanelReview = loadPanelReview;

async function loadPanelReview() {
  await loadProjectData(APP.projectName);
  const panels = APP.projectData?.panels || [];
  const pwt = APP.projectData?.panels_with_text || [];
  // Narrated mode reviews the CLEAN art panels (Crop 2); dialogue mode
  // reviews the bubble panels (Crop 1). Fall back if the preferred list
  // is empty so the step still shows something reviewable.
  const preferred = (APP.mode === 'narrated' || APP.mode === 'full_recap')
    ? (panels.length ? panels : pwt)
    : (pwt.length ? pwt : panels);
  const panelList = preferred;
  const grid = document.getElementById('panelReviewGrid');

  if (panelList.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🖼</div>
        <div class="empty-state-text">No panels found. Go back to Stitch step and run: Stitch Pages → Detect Panels → Crop Panels</div>
      </div>`;
    return;
  }

  // Create a grid of panel thumbnails with delete/crop actions
  grid.innerHTML = `
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px;">
      ${panelList.map((p, i) => {
        const pid = p.panel_id || (i + 1);
        const filename = p.path ? p.path.split('/').pop() : `${String(pid).padStart(4, '0')}.jpg`;
        const imgUrl = `/api/panel-image/${encodeURIComponent(APP.projectName)}/${filename}?t=${Date.now()}`;
        
        return `
          <div class="panel-review-card" id="review-card-${pid}" data-panel-id="${pid}" data-filename="${filename}">
            <div class="panel-badge">#${pid}</div>
            <img src="${imgUrl}" 
                 alt="Panel ${pid}" 
                 style="width: 100%; height: auto; display: block; border-radius: 4px; min-height: 150px; object-fit: cover;"
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div style="display: none; width: 100%; height: 200px; align-items: center; justify-content: center; background: var(--bg-secondary); border-radius: 4px; color: var(--text-dim); flex-direction: column; gap: 8px;">
              <span>⚠️</span>
              <span style="font-size: 12px;">Image not available</span>
            </div>
            <div style="margin-top: 6px; text-align: center; font-size: 12px; color: var(--text-secondary);">
              Panel ${pid}
            </div>
            <div class="panel-actions">
              <button class="btn-delete" onclick="deleteReviewPanel(${pid}, this)" title="Delete this panel">🗑️ Delete</button>
              <button onclick="openCropModal(${pid}, '${filename}')" title="Crop this panel">✂️ Crop</button>
            </div>
          </div>
        `;
      }).join('')}
    </div>`;

  document.getElementById('panelCount').textContent = `${panelList.length} panels cropped and ready`;
  console.log('Loaded panels:', panelList.length, 'Sample panel:', panelList[0]);
}

// ─── Delete Panel ───────────────────────────────────────
async function deleteReviewPanel(pid, btn) {
  if (!confirm(`Delete Panel #${pid}? This will permanently remove the panel image.`)) return;
  
  const card = document.getElementById(`review-card-${pid}`);
  if (card) card.classList.add('deleting');

  try {
    const resp = await fetch(`/api/panels/${encodeURIComponent(APP.projectName)}/${pid}`, {
      method: 'DELETE',
    });
    const data = await resp.json();
    if (resp.ok) {
      toast(`✅ Panel #${pid} deleted (${data.remaining} remaining)`, 'success');
      // Wait for animation then reload
      setTimeout(() => loadPanelReview(), 350);
    } else {
      toast(`Delete failed: ${data.error}`, 'error');
      if (card) card.classList.remove('deleting');
    }
  } catch (e) {
    toast('Delete failed: ' + e.message, 'error');
    if (card) card.classList.remove('deleting');
  }
}

// ─── Crop Modal ─────────────────────────────────────────
let cropState = { panelId: null, filename: null, natW: 0, natH: 0, startX: 0, startY: 0, drawing: false, selection: null };

function openCropModal(pid, filename) {
  cropState = { panelId: pid, filename, natW: 0, natH: 0, startX: 0, startY: 0, drawing: false, selection: null };
  
  const imgUrl = `/api/panel-image/${encodeURIComponent(APP.projectName)}/${filename}?t=${Date.now()}`;
  
  // Create modal overlay
  let overlay = document.getElementById('cropModalOverlay');
  if (overlay) overlay.remove();
  
  overlay = document.createElement('div');
  overlay.id = 'cropModalOverlay';
  overlay.className = 'crop-modal-overlay';
  overlay.innerHTML = `
    <div class="crop-modal-header">
      <div>
        <div class="crop-title">✂️ Crop Panel #${pid}</div>
        <div class="crop-hint">Click and drag to select the area you want to KEEP</div>
      </div>
      <button class="btn btn-ghost" onclick="closeCropModal()" style="color: white;">✕ Cancel</button>
    </div>
    <div class="crop-container">
      <div class="crop-image-wrapper" id="cropImageWrapper">
        <img id="cropModalImage" src="${imgUrl}" alt="Panel ${pid}"
             onload="onCropImageLoad(this)">
      </div>
    </div>
    <div class="crop-modal-actions">
      <button class="btn btn-ghost" onclick="closeCropModal()">Cancel</button>
      <button class="btn btn-ghost" onclick="resetCropSelection()">↺ Reset Selection</button>
      <button class="btn btn-primary" id="btnApplyCrop" onclick="applyCrop()" disabled>✂️ Apply Crop</button>
    </div>
  `;
  
  document.body.appendChild(overlay);
  document.body.style.overflow = 'hidden';
}

function onCropImageLoad(img) {
  cropState.natW = img.naturalWidth;
  cropState.natH = img.naturalHeight;
  
  const wrapper = document.getElementById('cropImageWrapper');
  wrapper.addEventListener('mousedown', cropMouseDown);
  wrapper.addEventListener('mousemove', cropMouseMove);
  wrapper.addEventListener('mouseup', cropMouseUp);
}

function cropMouseDown(e) {
  if (e.target.tagName === 'BUTTON') return;
  e.preventDefault();
  const wrapper = document.getElementById('cropImageWrapper');
  const rect = wrapper.getBoundingClientRect();
  
  cropState.startX = e.clientX - rect.left;
  cropState.startY = e.clientY - rect.top;
  cropState.drawing = true;
  
  // Remove existing selection
  const existing = wrapper.querySelector('.crop-selection');
  if (existing) existing.remove();
  
  // Create selection box
  const sel = document.createElement('div');
  sel.className = 'crop-selection';
  sel.style.left = cropState.startX + 'px';
  sel.style.top = cropState.startY + 'px';
  sel.style.width = '0px';
  sel.style.height = '0px';
  wrapper.appendChild(sel);
  cropState.selection = sel;
}

function cropMouseMove(e) {
  if (!cropState.drawing || !cropState.selection) return;
  e.preventDefault();
  const wrapper = document.getElementById('cropImageWrapper');
  const rect = wrapper.getBoundingClientRect();
  
  const curX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
  const curY = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
  
  const x = Math.min(cropState.startX, curX);
  const y = Math.min(cropState.startY, curY);
  const w = Math.abs(curX - cropState.startX);
  const h = Math.abs(curY - cropState.startY);
  
  cropState.selection.style.left = x + 'px';
  cropState.selection.style.top = y + 'px';
  cropState.selection.style.width = w + 'px';
  cropState.selection.style.height = h + 'px';
}

function cropMouseUp(e) {
  if (!cropState.drawing) return;
  cropState.drawing = false;
  
  // Enable apply button if selection is large enough
  const sel = cropState.selection;
  if (sel) {
    const w = parseFloat(sel.style.width);
    const h = parseFloat(sel.style.height);
    const btn = document.getElementById('btnApplyCrop');
    if (btn) btn.disabled = (w < 10 || h < 10);
  }
}

function resetCropSelection() {
  const wrapper = document.getElementById('cropImageWrapper');
  const existing = wrapper?.querySelector('.crop-selection');
  if (existing) existing.remove();
  cropState.selection = null;
  const btn = document.getElementById('btnApplyCrop');
  if (btn) btn.disabled = true;
}

async function applyCrop() {
  if (!cropState.selection || !cropState.panelId) return;
  
  const wrapper = document.getElementById('cropImageWrapper');
  const img = document.getElementById('cropModalImage');
  const sel = cropState.selection;
  
  // Convert display coordinates to natural image coordinates
  const displayW = img.clientWidth;
  const displayH = img.clientHeight;
  const scaleX = cropState.natW / displayW;
  const scaleY = cropState.natH / displayH;
  
  const x = Math.round(parseFloat(sel.style.left) * scaleX);
  const y = Math.round(parseFloat(sel.style.top) * scaleY);
  const w = Math.round(parseFloat(sel.style.width) * scaleX);
  const h = Math.round(parseFloat(sel.style.height) * scaleY);
  
  if (w < 10 || h < 10) {
    toast('Selection too small', 'error');
    return;
  }
  
  try {
    const resp = await fetch(`/api/panels/${encodeURIComponent(APP.projectName)}/${cropState.panelId}/crop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x, y, w, h }),
    });
    const data = await resp.json();
    if (resp.ok) {
      toast(`✅ Panel #${cropState.panelId} cropped to ${data.new_width}×${data.new_height}`, 'success');
      closeCropModal();
      
      // Force reload project data to get fresh image paths
      APP.projectData = null;
      await loadProjectData(APP.projectName, true); // Force refresh
      
      // Reload the current review step
      if (APP.currentStep === 'review') {
        loadPanelReview();
      } else if (APP.currentStep === 'review2') {
        loadPanelTextReview();
      }
    } else {
      toast(`Crop failed: ${data.error}`, 'error');
    }
  } catch (e) {
    toast('Crop failed: ' + e.message, 'error');
  }
}

function closeCropModal() {
  const overlay = document.getElementById('cropModalOverlay');
  if (overlay) overlay.remove();
  document.body.style.overflow = '';
  cropState = { panelId: null, filename: null, natW: 0, natH: 0, startX: 0, startY: 0, drawing: false, selection: null };
}

// ─── Step: Review 2 (Text Review) ───────────────────────────────
function renderReview2Step() {
  const isNarrated = APP.mode === 'narrated';
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>

    ${isNarrated ? `
    <p class="text-sm text-dim mb-1">
      Review the narration for each art panel (the clean panels without bubble text).
      Edit the text directly, or hit 🔁 Re-narrate to regenerate just that panel with AI.
    </p>` : `
    <p class="text-sm text-dim mb-1">
      Review the dialogue extracted from each panel's speech bubbles.
      Этот текст используется как контекст для сценариста. Исправьте ошибки распознавания, чтобы пересказ точнее передавал сюжет.
    </p>`}
    <div id="panelTextReviewList" style="margin-top: 20px;">
      <div class="empty-state">
        <div class="spinner spinner-lg" style="margin:0 auto 12px"></div>
        <div class="empty-state-text">Loading ${isNarrated ? 'narration' : 'dialogue text'} review...</div>
      </div>
    </div>
    <div id="panelTextCount" class="text-xs text-dim mt-1"></div>`;

  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-primary" onclick="nextStep()">${isNarrated ? 'Narration Looks Good, Continue →' : 'Text Looks Good, Continue →'}</button>
    </div>`;

  loadNarrationReview();
}
window.renderReview2Step = renderReview2Step;

async function loadNarrationReview() {
  await loadProjectData(APP.projectName);
  const isNarrated = APP.mode === 'narrated';
  const container = document.getElementById('panelTextReviewList');

  if (!isNarrated) {
    await loadDialogueTextReview(container);
    return;
  }

  // ✅ Narrated flow: art panels (Crop 2) carry the narration
  const panels = APP.projectData?.panels || [];
  const withNarration = panels.filter(p => p.narration || p.scene_narration);
  const panelList = withNarration.length > 0 ? panels : [];

  if (panelList.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🎭</div>
        <div class="empty-state-text">No narrations yet. Go back and run "Generate Narration" first.</div>
      </div>`;
    return;
  }

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 24px; max-height: 620px; overflow-y: auto; padding-right: 8px;">
      ${panelList.map((p, i) => {
        const pid = p.panel_id || (i + 1);
        const filename = p.path ? p.path.split('/').pop() : `${String(pid).padStart(4, '0')}.jpg`;
        const imgUrl = `/api/panel-image/${encodeURIComponent(APP.projectName)}/${filename}`;
        const narration = p.narration || p.scene_narration || '';
        return `
          <div style="border: 1px solid var(--border); border-radius: 12px; padding: 20px; background: var(--bg-card); display: flex; flex-wrap: wrap; gap: 20px; align-items: start;">
            <div style="flex: 0 0 180px; max-width: 180px;">
              <div style="background: rgba(0,0,0,0.7); color: white; padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; margin-bottom: 12px; text-align: center;">
                Panel #${pid}
              </div>
              <img src="${imgUrl}" alt="Panel ${pid}"
                   style="width: 100%; height: auto; display: block; border-radius: 8px; border: 2px solid var(--border);"
                   onerror="this.style.display='none'">
              ${p.text ? `<div style="margin-top:8px; font-size:11px; color:var(--text-dim); max-height:90px; overflow-y:auto;"><strong>Dialogue:</strong><br>${esc(p.text)}</div>` : ''}
            </div>
            <div style="flex: 1 1 320px; min-width: 280px;">
              <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                🎭 Narration
              </div>
              <textarea id="narr_edit_${pid}" rows="4"
                style="width:100%; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-size: 14px; line-height: 1.6; color: var(--text-primary); resize: vertical; font-family: inherit;">${esc(narration)}</textarea>
              <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
                <button class="btn btn-secondary" style="padding:6px 14px; font-size:12px;" onclick="savePanelNarration(${pid})">💾 Save Text</button>
                <button class="btn btn-secondary" style="padding:6px 14px; font-size:12px;" onclick="renarratePanel(${pid})" id="btnRenarr_${pid}">🔁 Re-narrate this panel</button>
                <span id="narr_status_${pid}" class="text-xs text-dim" style="align-self:center;"></span>
              </div>
            </div>
          </div>`;
      }).join('')}
    </div>`;
  document.getElementById('panelTextCount').textContent = `${panelList.length} narrated panel(s)`;
}

// ─── Dialogue mode: review the EXTRACTED dialogue per bubble panel ──────
async function loadDialogueTextReview(container) {
  const pwt = APP.projectData?.panels_with_text || [];

  if (pwt.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">💬</div>
        <div class="empty-state-text">No extracted text yet. Go back and run "Extract Dialogue" first.</div>
      </div>`;
    document.getElementById('panelTextCount').textContent = '';
    return;
  }

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 24px; max-height: 620px; overflow-y: auto; padding-right: 8px;">
      ${pwt.map((p, i) => {
        const pid = p.panel_id || (i + 1);
        const filename = p.path ? p.path.split('/').pop() : `${String(pid).padStart(4, '0')}.jpg`;
        const imgUrl = `/api/panel-image/${encodeURIComponent(APP.projectName)}/${filename}`;
        const text = p.text || p.dialogue || '';
        return `
          <div style="border: 1px solid var(--border); border-radius: 12px; padding: 20px; background: var(--bg-card); display: flex; flex-wrap: wrap; gap: 20px; align-items: start;">
            <div style="flex: 0 0 180px; max-width: 180px;">
              <div style="background: rgba(0,0,0,0.7); color: white; padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; margin-bottom: 12px; text-align: center;">
                Panel #${pid}
              </div>
              <img src="${imgUrl}" alt="Panel ${pid}"
                   style="width: 100%; height: auto; display: block; border-radius: 8px; border: 2px solid var(--border);"
                   onerror="this.style.display='none'">
            </div>
            <div style="flex: 1 1 320px; min-width: 280px;">
              <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                💬 Extracted Dialogue
              </div>
              <textarea id="dlg_edit_${pid}" rows="4"
                style="width:100%; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-size: 14px; line-height: 1.6; color: var(--text-primary); resize: vertical; font-family: inherit;">${esc(text)}</textarea>
              <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
                <button class="btn btn-secondary" style="padding:6px 14px; font-size:12px;" onclick="savePanelDialogue(${pid})">💾 Save Text</button>
                <span id="dlg_status_${pid}" class="text-xs text-dim" style="align-self:center;"></span>
              </div>
            </div>
          </div>`;
      }).join('')}
    </div>`;
  document.getElementById('panelTextCount').textContent = `${pwt.length} панелей с текстовым контекстом для сценария`;
}

async function savePanelDialogue(panelId) {
  const text = (document.getElementById(`dlg_edit_${panelId}`) || {}).value ?? '';
  const status = document.getElementById(`dlg_status_${panelId}`);
  try {
    const r = await fetch(`/api/panels/${encodeURIComponent(APP.projectName)}/${panelId}/text`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error((await r.json()).error || r.status);
    if (status) status.textContent = '✓ saved';
    toast(`Panel #${panelId} dialogue saved`, 'success');
  } catch (e) {
    if (status) status.textContent = '✗ save failed';
    toast('Save failed: ' + e.message, 'error');
  }
}

async function savePanelNarration(panelId) {
  const text = (document.getElementById(`narr_edit_${panelId}`) || {}).value ?? '';
  const status = document.getElementById(`narr_status_${panelId}`);
  try {
    const r = await fetch(`/api/panels/${encodeURIComponent(APP.projectName)}/${panelId}/narration`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ narration: text }),
    });
    if (!r.ok) throw new Error((await r.json()).error || r.status);
    if (status) status.textContent = '✓ saved';
    toast(`Panel #${panelId} narration saved`, 'success');
  } catch (e) {
    if (status) status.textContent = '✗ save failed';
    toast('Save failed: ' + e.message, 'error');
  }
}

async function renarratePanel(panelId) {
  const status = document.getElementById(`narr_status_${panelId}`);
  const btn = document.getElementById(`btnRenarr_${panelId}`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Re-narrating…'; }
  if (status) status.textContent = 'AI is re-narrating this panel…';
  try {
    const r = await fetch(`/api/panels/${encodeURIComponent(APP.projectName)}/${panelId}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.status);
    if (!data.narration || data.narration.startsWith('[')) throw new Error(data.narration || 'model returned empty');
    const ta = document.getElementById(`narr_edit_${panelId}`);
    if (ta) ta.value = data.narration;
    if (status) status.textContent = '✓ re-narrated';
    toast(`Panel #${panelId} re-narrated`, 'success');
  } catch (e) {
    if (status) status.textContent = '✗ re-narrate failed';
    toast('Re-narrate failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🔁 Re-narrate this panel'; }
  }
}

async function loadPanelTextReview() {
  await loadProjectData(APP.projectName);
  const panels = APP.projectData?.panels || [];
  const pwt = APP.projectData?.panels_with_text || [];
  const panelList = pwt.length > 0 ? pwt : panels;
  const container = document.getElementById('panelTextReviewList');

  if (panelList.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📝</div>
        <div class="empty-state-text">No panels found. Go back and extract text first.</div>
      </div>`;
    return;
  }

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 24px; max-height: 600px; overflow-y: auto; padding-right: 8px;">
      ${panelList.map((p, i) => {
        const pid = p.panel_id || (i + 1);
        const filename = p.path ? p.path.split('/').pop() : `${String(pid).padStart(4, '0')}.jpg`;
        const imgUrl = `/api/panel-image/${encodeURIComponent(APP.projectName)}/${filename}?t=${Date.now()}`;
        const text = p.text || p.dialogue || '';
        const hasText = text && text.trim();
        
        return `
          <div style="border: 1px solid var(--border); border-radius: 12px; padding: 20px; background: var(--bg-card); display: flex; flex-wrap: wrap; gap: 20px; align-items: start;">
            <div style="flex-shrink: 0; width: 200px;">
              <div style="background: rgba(0,0,0,0.7); color: white; padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; margin-bottom: 12px; text-align: center;">
                Panel #${pid}
              </div>
              <img src="${imgUrl}" 
                   alt="Panel ${pid}" 
                   style="width: 100%; height: auto; display: block; border-radius: 8px; border: 2px solid var(--border);"
                   onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
              <div style="display: none; width: 100%; height: 200px; align-items: center; justify-content: center; background: var(--bg-secondary); border-radius: 8px; color: var(--text-dim); flex-direction: column; gap: 8px; border: 2px solid var(--border);">
                <span style="font-size: 24px;">⚠️</span>
                <span style="font-size: 12px;">Image not available</span>
              </div>
            </div>
            <div style="flex: 1 1 320px; min-width: 280px;">
              <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                Extracted Text
              </div>
              <div style="background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 16px; min-height: 100px; font-size: 14px; line-height: 1.6; color: var(--text-primary); white-space: pre-wrap;">
                ${hasText ? esc(text) : '<span style="color: var(--text-dim); font-style: italic;">No text extracted</span>'}
              </div>
              ${hasText ? `<div style="margin-top: 8px; font-size: 12px; color: var(--color-success);">✓ Text extracted (${text.length} chars)</div>` : '<div style="margin-top: 8px; font-size: 12px; color: var(--color-warning);">⚠️ No text found</div>'}
            </div>
          </div>
        `;
      }).join('')}
    </div>`;

  const withText = panelList.filter(p => (p.text || p.dialogue || '').trim()).length;
  document.getElementById('panelTextCount').textContent = `${panelList.length} panels • ${withText} with extracted text`;
}
window.loadPanelTextReview = loadPanelTextReview;

// ─── Step: Extract Text ─────────────────────────────────
function renderExtractStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>
    
    <p class="text-sm text-dim mb-2">
      Extract dialogue text from speech bubbles using AI vision (qwen2.5vl).
      This reads the text in each panel's speech bubbles.
    </p>
    <div class="progress-container hidden" id="extractProgress">
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="extractProgressBar"></div></div>
      <div class="progress-label">
        <span id="extractProgressMsg">Extracting...</span>
        <span class="pct" id="extractProgressPct">0%</span>
      </div>
    </div>
    <div id="extractedTextPreview" class="mt-2"></div>`;

  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-secondary" onclick="runExtractText()" id="btnExtract">🔍 Extract Dialogue</button>
      <button class="btn btn-primary" onclick="nextStep()" id="btnExtractNext">Continue →</button>
    </div>`;

  // Check if already done
  loadProjectData(APP.projectName).then(() => {
    if (APP.projectData) {
      const pwt = APP.projectData.panels_with_text || APP.projectData.panels || [];
      const hasText = pwt.some(p => p.text || p.dialogue);
      if (hasText) {
        renderExtractedTexts(pwt);
      }
    }
  });
}

async function runExtractText() {
  setRunning(true, 'Extracting dialogue...');
  showProgress('extract');
  try {
    await fetch('/api/run/step/extract_dialogue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
  } catch (e) { toast('Extract failed: ' + e.message, 'error'); setRunning(false); }
}

function renderExtractedTexts(panels) {
  const el = document.getElementById('extractedTextPreview');
  if (!el) return;
  const items = panels.filter(p => p.text || p.dialogue).slice(0, 20);
  if (items.length === 0) return;

  el.innerHTML = `
    <div class="settings-panel-title">📝 Extracted Text Preview</div>
    <div class="narration-list">
      ${items.map(p => {
        const pid = p.panel_id || 0;
        const text = p.text || p.dialogue || '';
        const imgUrl = `/api/panel-image/${encodeURIComponent(APP.projectName)}/panel_${String(pid).padStart(4, '0')}.jpg`;
        return `
          <div class="narration-item">
            <img class="narration-item-img" src="${imgUrl}" alt="Panel ${pid}"
                 onerror="this.style.display='none'">
            <div class="narration-item-content">
              <div class="narration-item-id">Panel ${pid}</div>
              <div class="text-sm">${esc(text.substring(0, 200))}</div>
            </div>
          </div>`;
      }).join('')}
    </div>
    ${items.length < panels.length ? `<div class="text-xs text-dim mt-1">Showing ${items.length} of ${panels.length} panels</div>` : ''}`;
}

// ─── Step: Clean (Narrated mode only) ───────────────────
function renderCleanStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>
    
    <p class="text-sm text-dim mb-2">
      Remove speech bubble text from panels to create clean artwork.
      These clean panels will be used in the final narrated video.
    </p>
    <div class="progress-container hidden" id="cleanProgress">
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="cleanProgressBar"></div></div>
      <div class="progress-label">
        <span id="cleanProgressMsg">Removing text...</span>
        <span class="pct" id="cleanProgressPct">0%</span>
      </div>
    </div>
    <div id="cleanPreview" class="mt-2"></div>`;

  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-secondary" onclick="runClean()" id="btnClean">🧹 Remove Text</button>
      <button class="btn btn-primary" onclick="nextStep()" id="btnCleanNext">Continue →</button>
    </div>`;
}

async function runClean() {
  setRunning(true, 'Removing text from panels...');
  showProgress('clean');
  try {
    await fetch('/api/run/step/remove_text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: APP.projectName }),
    });
  } catch (e) { toast('Clean failed: ' + e.message, 'error'); setRunning(false); }
}

// ─── Step: Narrate (Narrated mode only) ─────────────────
// ─── 🎭 Cast Builder (Narrated mode, optional) ───────────
APP.castSession = null;   // {session_id, faces}
APP.castSelection = new Set();
APP.castCharacters = [];

function renderCastStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>

    <p class="text-sm text-dim mb-2">
      Optional but recommended: scan your downloaded chapters to extract character faces,
      group them into characters, and give each an ID with a name and gender.
      The narrator then uses real names instead of "a dark-haired guy". You can skip this entirely.
    </p>

    <div style="display:grid; grid-template-columns: 1.1fr 1.3fr 1.1fr; gap:14px; align-items:start;">

      <!-- ═══ Panel 1: Detected Faces ═══ -->
      <div class="settings-panel" style="margin:0; padding:14px;">
        <div class="settings-panel-title" style="margin-bottom:10px;">🔎 Detected Faces</div>
        <div style="display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
          <button class="btn btn-secondary" onclick="castScanChapters()" id="btnCastScan" style="flex:1; padding:8px 10px; font-size:12.5px;">📷 Load Images, Detect Faces</button>
        </div>
        <div id="castScanStatus" class="text-xs text-dim" style="margin-bottom:10px; min-height:16px;"></div>
        <div id="castFacesGrid"
             style="display:grid; grid-template-columns:repeat(auto-fill, minmax(84px, 1fr)); gap:8px;
                    max-height:430px; overflow-y:auto; padding:8px; background:var(--bg-secondary); border-radius:10px; min-height:120px;">
          <div class="text-xs text-dim" style="grid-column:1/-1; text-align:center; padding:24px 8px;">
            No scan yet — click <strong>Load Images, Detect Faces</strong> above.
          </div>
        </div>
        <div class="text-xs text-dim" style="margin-top:8px;">Click faces to select · click again to deselect</div>
      </div>

      <!-- ═══ Panel 2: Character ID Builder ═══ -->
      <div class="settings-panel" style="margin:0; padding:14px;">
        <div class="settings-panel-title" style="margin-bottom:10px;">🧩 Character ID Builder</div>

        <div class="text-xs text-dim" style="margin-bottom:6px;">Selected Reference Character Images:</div>
        <div id="castSelectionStrip"
             style="display:flex; flex-wrap:wrap; gap:6px; min-height:64px; max-height:140px; overflow-y:auto;
                    padding:8px; background:var(--bg-secondary); border:1px solid var(--border); border-radius:10px; margin-bottom:14px;">
          <span class="text-xs text-dim" style="align-self:center;">Nothing selected yet</span>
        </div>

        <div class="form-group" style="margin-bottom:10px;">
          <label class="form-label">Name:</label>
          <input class="form-input" id="castCharName" placeholder="Character name (e.g. Ken Shadow)">
        </div>
        <div class="form-group" style="margin-bottom:14px;">
          <label class="form-label">Gender:</label>
          <select class="form-select" id="castCharGender">
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="unknown">Unknown</option>
          </select>
        </div>

        <div style="display:flex; gap:8px; margin-bottom:10px;">
          <button class="btn btn-ghost" onclick="castClearSelection()" style="flex:1;">Clear</button>
          <button class="btn" style="flex:1; background:var(--blue); color:#fff; font-weight:700;" onclick="castAddCharacter()" id="btnCastAdd">💾 Save</button>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-secondary" onclick="castImport()" style="flex:1; font-size:12px;">📥 Import Cast File</button>
          <button class="btn btn-secondary" onclick="castExport()" style="flex:1; font-size:12px;">📤 Export Cast File</button>
        </div>
        <input type="file" id="castImportFile" accept=".zip" style="display:none" onchange="castImportFileSelected(event)">

        <div style="border-top:1px solid var(--border); margin:16px 0 12px;"></div>
        <div class="settings-panel-title" style="margin-bottom:8px; font-size:13px;">🌐 Import from MyAnimeList</div>
        <div class="form-group" style="margin-bottom:8px;">
          <input class="form-input" id="castMalUrl" placeholder="https://myanimelist.net/manga/.../characters" style="font-size:12px;">
          <div class="text-xs text-dim" style="margin-top:4px;">Paste the manhwa's MAL page URL — names, roles and profile images are pulled automatically into this cast.</div>
        </div>
        <button class="btn btn-secondary" onclick="castImportFromMAL()" id="btnCastMal" style="width:100%; font-size:12.5px;">🌐 Import Cast from MAL</button>
        <div id="castMalStatus" class="text-xs" style="margin-top:6px; min-height:16px;"></div>
        <details style="margin-top:8px;">
          <summary class="text-xs text-dim" style="cursor:pointer;">Or type names manually</summary>
          <div class="form-group" style="margin-top:8px;">
            <textarea class="form-input" id="castBulkNames" rows="2" placeholder="Nan Hao, Shang Feng, Xue" style="font-size:12px;"></textarea>
          </div>
          <button class="btn btn-ghost" onclick="castBulkAdd()" style="width:100%; font-size:12px;">➕ Add These Names</button>
        </details>
      </div>

      <!-- ═══ Panel 3: Saved Characters ═══ -->
      <div class="settings-panel" style="margin:0; padding:14px;">
        <div class="settings-panel-title" style="margin-bottom:10px;">🗂️ Saved Characters ID</div>
        <div id="castCharactersList" style="display:flex; flex-direction:column; gap:10px; max-height:470px; overflow-y:auto;"></div>
      </div>
    </div>`;

  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-secondary" onclick="castSkip()">Skip — no cast</button>
      <button class="btn btn-primary" onclick="nextStep()">Continue →</button>
    </div>`;

  // Load any previously saved characters for this project
  loadCastCharacters();
}
window.renderCastStep = renderCastStep;

function castNameForProject() {
  return (APP.projectName || 'project').toLowerCase().replace(/ /g, '-') + '-cast';
}

// ─── Scan: detect faces from downloaded chapters ─────────
async function castScanChapters() {
  if (isPipelineBusy()) return;
  const status = document.getElementById('castScanStatus');
  const btn = document.getElementById('btnCastScan');
  try {
    // Resolve the on-disk manga folder — the project name may contain spaces
    // while download folders use hyphens ("Nan Hao..." → "Nan-Hao-...")
    const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    let downloaded = [];
    try {
      downloaded = await (await fetch('/api/scraper/downloaded')).json() || [];
    } catch (e) { /* ignore */ }
    let match = downloaded.find(m => norm(m.name) === norm(APP.projectName));
    if (!match && downloaded.length === 1 && !APP.projectName) {
      // No project name given — if exactly one manhwa is downloaded, use it
      match = downloaded[0];
      APP.projectName = match.name.replace(/-/g, ' ');
    }
    if (!match && APP.projectName) {
      // Fall back to a partial (prefix/substring) name match
      match = downloaded.find(m =>
        norm(m.name).includes(norm(APP.projectName)) ||
        norm(APP.projectName).includes(norm(m.name)));
    }
    let mangaPath = match ? match.path : '';
    if (!mangaPath) {
      const root = (await (await fetch('/api/scraper/download-root')).json()).path;
      mangaPath = `${root}/${(APP.projectName || '').replace(/ /g, '-')}`;
    }

    // Chapters to sample: prefer pipeline state (if it has real chapters);
    // otherwise derive chapter numbers from the downloaded folder names.
    // NOTE: never call loadProjectData here — it would create a phantom
    // project folder for a display name that doesn't exist on disk.
    let chapters = ((APP.projectData && APP.projectData.chapter_list) || [])
      .filter(n => Number(n) > 0);
    if (chapters.length === 0 && match && Array.isArray(match.chapter_list)) {
      chapters = match.chapter_list
        .map(name => { const mnum = String(name).match(/(\d+)/); return mnum ? parseInt(mnum[1], 10) : null; })
        .filter(n => n !== null && n > 0);
    }
    if (chapters.length === 0) {
      if (status) status.innerHTML = '❌ No downloaded chapters found — download chapters in the Source step first.';
      toast('No downloaded chapters found — download chapters first', 'error');
      return;
    }
    const sampleSize = Math.min(4, chapters.length);
    const start = chapters[Math.floor(Math.random() * Math.max(1, chapters.length - sampleSize + 1))];
    const sample = chapters.filter(c => c >= start && c <= start + sampleSize - 1);
    const from = Math.min(...sample);
    const to = Math.max(...sample);

    if (status) status.innerHTML = `🔍 Scanning chapters ${from}–${to} for character faces… (this can take a minute)`;
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Scanning…'; }
    setRunning(true, 'Scanning faces...');

    // NOTE: the scan runs in the background — the result arrives via the
    // socket 'step_complete' event (step: 'char_scan') and is handled there.
    await fetch('/api/charbuilder/scan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manga_path: mangaPath, chapter_from: from, chapter_to: to }),
    });
  } catch (e) {
    if (status) status.textContent = '❌ Scan failed: ' + e.message;
    const btn = document.getElementById('btnCastScan');
    if (btn) { btn.disabled = false; btn.textContent = '📷 Load Images, Detect Faces'; }
    setRunning(false);
  }
}

// Socket delivery for the scan result (registered once at startup)
if (!window._castScanSocketHooked) {
  window._castScanSocketHooked = true;
  socket.on('step_complete', (data) => {
    if (data.step !== 'char_scan') return;
    const status = document.getElementById('castScanStatus');
    const btn = document.getElementById('btnCastScan');
    if (btn) { btn.disabled = false; btn.textContent = '📷 Load Images, Detect Faces'; }
    if (data.error) {
      if (status) status.innerHTML = '❌ ' + esc(data.error);
      setRunning(false);
      return;
    }
    APP.castSession = data.result || null;
    APP.castSelection = new Set();
    setRunning(false);
    if (APP.castSession && Array.isArray(APP.castSession.faces)) {
      renderCastFaces();
      renderCastSelection();
      if (status) status.innerHTML = `✅ Found ${APP.castSession.faces.length} faces from chapters ${APP.castSession.chapters || ''}. Click faces of the same character, then Save with a name.`;
    } else {
      if (status) status.innerHTML = '⚠️ Scan finished but found no faces. Try more chapters or check the images.';
    }
  });
}

// ─── Faces grid + selection ──────────────────────────────
function renderCastFaces() {
  const grid = document.getElementById('castFacesGrid');
  if (!grid) return;
  const faces = (APP.castSession && APP.castSession.faces) || [];
  if (faces.length === 0) {
    grid.innerHTML = '<div class="text-xs text-dim" style="grid-column:1/-1; text-align:center; padding:24px 8px;">No faces detected.</div>';
    return;
  }
  grid.innerHTML = faces.map(f => {
    const idx = f.index !== undefined ? f.index : f.idx;
    const url = `/api/charbuilder/face/${APP.castSession.session_id}/${f.filename}`;
    const selected = APP.castSelection.has(idx);
    return `
      <div data-face-idx="${idx}" onclick="toggleCastFace(${idx})"
           style="cursor:pointer; position:relative; border:3px solid ${selected ? 'var(--blue)' : 'transparent'};
                  border-radius:10px; overflow:hidden; background:var(--bg-card);">
        <img src="${url}" style="width:100%; aspect-ratio:1; object-fit:cover; display:block;">
        <div style="position:absolute; top:3px; left:3px; padding:0 6px; border-radius:6px;
                    font-size:10px; font-weight:800; color:#fff; background:rgba(0,0,0,0.65);">#${idx}</div>
        ${selected ? '<div style="position:absolute; bottom:3px; right:3px; font-size:11px;">✅</div>' : ''}
      </div>`;
  }).join('');
}

function renderCastSelection() {
  const strip = document.getElementById('castSelectionStrip');
  if (!strip) return;
  const faces = (APP.castSession && APP.castSession.faces) || [];
  const selected = Array.from(APP.castSelection).sort((a, b) => a - b);
  if (selected.length === 0) {
    strip.innerHTML = '<span class="text-xs text-dim" style="align-self:center;">Nothing selected yet</span>';
    return;
  }
  strip.innerHTML = selected.map(idx => {
    const f = faces.find(x => (x.index !== undefined ? x.index : x.idx) === idx);
    if (!f) return '';
    const url = `/api/charbuilder/face/${APP.castSession.session_id}/${f.filename}`;
    return `
      <div onclick="toggleCastFace(${idx})" title="Click to remove"
           style="cursor:pointer; width:52px; height:52px; border-radius:8px; overflow:hidden; border:2px solid var(--blue);">
        <img src="${url}" style="width:100%; height:100%; object-fit:cover; display:block;">
      </div>`;
  }).join('');
}

function toggleCastFace(idx) {
  if (APP.castSelection.has(idx)) APP.castSelection.delete(idx);
  else APP.castSelection.add(idx);
  renderCastFaces();
  renderCastSelection();
}

function castClearSelection() {
  APP.castSelection = new Set();
  renderCastFaces();
  renderCastSelection();
}

// ─── Save / Load / Delete characters ─────────────────────
async function castAddCharacter() {
  const name = (document.getElementById('castCharName') || {}).value?.trim();
  const gender = (document.getElementById('castCharGender') || {}).value || 'unknown';
  if (!name) return toast('Enter a character name', 'warning');
  if (APP.castSelection.size === 0) return toast('Select at least one face first', 'warning');
  if (!APP.castSession) return;
  const btn = document.getElementById('btnCastAdd'); if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/charbuilder/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cast_name: castNameForProject(),
        name, gender,
        face_indices: Array.from(APP.castSelection),
        session_id: APP.castSession.session_id,
      }),
    });
    const data = await r.json();
    if (data.error) { toast('Save failed: ' + data.error, 'error'); return; }
    await loadCastCharacters();
    castClearSelection();
    document.getElementById('castCharName').value = '';
    toast(`"${name}" saved as ${data.character.id}`, 'success');
  } finally {
    const btn = document.getElementById('btnCastAdd'); if (btn) btn.disabled = false;
  }
}

async function loadCastCharacters() {
  try {
    const r = await fetch(`/api/charbuilder/characters/${encodeURIComponent(castNameForProject())}`);
    const chars = await r.json();
    // load_characters returns a dict {char_id: {...}} — normalize to a list
    APP.castCharacters = Array.isArray(chars) ? chars : Object.values(chars || {});
  } catch (e) {
    APP.castCharacters = [];
  }
  renderCastCharacters();
}

function renderCastCharacters() {
  const list = document.getElementById('castCharactersList');
  if (!list) return;
  if (!APP.castCharacters.length) {
    list.innerHTML = '<div class="text-xs text-dim" style="text-align:center; padding:20px 6px;">No characters saved yet.<br>Scan faces, select a group, name it and hit Save.</div>';
    return;
  }
  list.innerHTML = APP.castCharacters.map(c => {
    const refs = c.reference_images || c.faces || [];
    const thumbs = refs.map(fname => `
      <img src="/api/charbuilder/charface/${castNameForProject()}/${fname}"
           style="width:40px; height:40px; object-fit:cover; border-radius:6px; border:1px solid var(--border);">`
    ).join('');
    return `
      <div style="border:1px solid var(--border); border-radius:12px; padding:12px; background:var(--bg-card);">
        <div style="font-size:12px; font-weight:700; margin-bottom:8px;">ID: ${esc(c.id || '')}</div>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px; max-height:92px; overflow-y:auto;">${thumbs || '<span class="text-xs text-dim">no reference images</span>'}</div>
        <div style="font-size:13px; font-weight:600; margin-bottom:2px;">Name: ${esc(c.name || '')}</div>
        <div style="font-size:13px; color:var(--text-secondary); margin-bottom:10px;">Gender: ${esc((c.gender || 'unknown').charAt(0).toUpperCase() + (c.gender || '').slice(1))}</div>
        <button class="btn btn-ghost" style="width:100%; padding:7px 0; font-size:12px; color:var(--color-error); border:1px solid var(--color-error); border-radius:6px;"
                onclick="castDeleteCharacter('${esc(c.id || '')}')">🗑️ Delete ID</button>
      </div>`;
  }).join('');
}

async function castDeleteCharacter(charId) {
  if (!charId) return;
  if (!confirm(`Delete character ${charId}? The narrator will no longer use this name.`)) return;
  try {
    const r = await fetch(`/api/charbuilder/character/${encodeURIComponent(castNameForProject())}/${encodeURIComponent(charId)}`, {
      method: 'DELETE',
    });
    if (!r.ok) throw new Error((await r.json()).error || r.status);
    await loadCastCharacters();
    toast(`Character ${charId} deleted`, 'success');
  } catch (e) {
    toast('Delete failed: ' + e.message, 'error');
  }
}

// ─── Import / Export cast archive ────────────────────────
function castExport() {
  window.open(`/api/charbuilder/export/${encodeURIComponent(castNameForProject())}`, '_blank');
}

function castImport() {
  const input = document.getElementById('castImportFile');
  if (input) input.click();
}

async function castImportFileSelected(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch(`/api/charbuilder/import/${encodeURIComponent(castNameForProject())}`, {
      method: 'POST', body: fd,
    });
    const data = await r.json();
    if (data.error) { toast('Import failed: ' + data.error, 'error'); return; }
    await loadCastCharacters();
    toast(`Imported cast (${data.characters} characters)`, 'success');
  } catch (e) {
    toast('Import failed: ' + e.message, 'error');
  } finally {
    ev.target.value = '';
  }
}

function castSkip() {
  toast('Cast skipped — narration will use generic descriptions', 'info');
  nextStep();
}

// ─── 🌐 Import cast from MyAnimeList ─────────────────────
// Input accepts: a MAL URL, a manhwa name (searched on MAL), or empty
// (auto-searched from the project name).
async function castImportFromMAL() {
  const urlInput = document.getElementById('castMalUrl');
  const status = document.getElementById('castMalStatus');
  const btn = document.getElementById('btnCastMal');
  let query = (urlInput?.value || '').trim();
  const isUrl = /^https?:\/\//i.test(query);

  if (!query) {
    query = APP.projectName || '';
    if (!query) {
      if (status) status.innerHTML = '❌ Paste a MyAnimeList URL or a manhwa name first';
      return;
    }
  }

  if (btn) { btn.disabled = true; btn.textContent = '⏳ Importing from MAL…'; }
  if (status) status.textContent = isUrl ? 'Fetching characters…' : `Searching MAL for "${query}"…`;
  try {
    // Resolve a name into the top MAL manga URL
    if (!isUrl) {
      const sr = await fetch(`/api/charbuilder/mal-search?q=${encodeURIComponent(query)}`);
      const sd = await sr.json();
      const top = (sd.results || [])[0];
      if (!top) {
        if (status) status.innerHTML = `❌ No manga found on MAL for "${esc(query)}" — paste the MAL URL directly`;
        return;
      }
      query = top.url;
      if (urlInput) urlInput.value = top.url;
      if (status) status.innerHTML = `Matched: <strong>${esc(top.name)}</strong> — fetching characters…`;
    }

    const r = await fetch('/api/charbuilder/import-from-mal', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mal_url: query, cast_name: castNameForProject(), max_characters: 20 }),
    });
    const data = await r.json();
    if (data.error) {
      if (status) status.innerHTML = '❌ ' + esc(data.error);
      toast('MAL import failed: ' + data.error, 'error');
      return;
    }
    await loadCastCharacters();
    if (status) status.innerHTML = `✅ Imported ${data.imported} character(s) — ${data.total} in cast (names, roles & images)`;
    toast(`Imported ${data.imported} characters from MyAnimeList`, 'success');
  } catch (e) {
    if (status) status.innerHTML = '❌ ' + esc(e.message);
    toast('MAL import failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🌐 Import Cast from MAL'; }
  }
}

async function castBulkAdd() {
  const raw = (document.getElementById('castBulkNames') || {}).value || '';
  const names = raw.split(/[,\n]+/).map(s => s.trim()).filter(Boolean);
  if (!names.length) { toast('Type at least one name', 'warning'); return; }
  try {
    const r = await fetch('/api/charbuilder/add-bulk', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cast_name: castNameForProject(), names }),
    });
    const data = await r.json();
    if (data.error) { toast('Bulk add failed: ' + data.error, 'error'); return; }
    await loadCastCharacters();
    document.getElementById('castBulkNames').value = '';
    toast(`Added ${data.added} character(s) — ${data.total} total`, 'success');
  } catch (e) {
    toast('Bulk add failed: ' + e.message, 'error');
  }
}
window.castImportFromMAL = castImportFromMAL;
window.castBulkAdd = castBulkAdd;

async function loadFullRecapData() {
  if (!APP.projectName) return null;
  try {
    const response = await fetch(`/api/full-recap/${encodeURIComponent(APP.projectName)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось загрузить данные Full Recap");
    FULL_RECAP_DATA = data;
    return data;
  } catch (error) {
    console.error("[FullRecap] Load failed:", error);
    return null;
  }
}

async function startFullRecapStep(step, settings = {}) {
  if (isPipelineBusy()) return;
  setRunning(true, "Full Recap: " + step);
  try {
    if (Object.keys(settings).length) {
      await fetch(`/api/projects/${encodeURIComponent(APP.projectName)}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
    }
    const response = await fetch(`/api/run/step/${step}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_name: APP.projectName, settings }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось запустить этап");
    toast("Этап запущен. Прогресс отображается в приложении.", "info");
  } catch (error) {
    setRunning(false);
    toast("Full Recap: " + error.message, "error");
  }
}

function renderFullRecapScriptPreview() {
  const el = document.getElementById("fullRecapScriptPreview");
  if (!el) return;
  const text = FULL_RECAP_DATA?.script || "";
  el.value = text;
  const meta = document.getElementById("fullRecapScriptMeta");
  if (meta) {
    const words = Number(FULL_RECAP_DATA?.word_count || (text.match(/[A-Za-zА-Яа-яЁё0-9]+(?:[’'-][A-Za-zА-Яа-яЁё0-9]+)*/gu) || []).length);
    const duration = Number(FULL_RECAP_DATA?.duration_seconds || words * 0.72);
    meta.textContent = text
      ? `${words.toLocaleString("ru-RU")} слов · расчётная длительность немого видео: ${formatRecapDuration(duration)}`
      : "Сценарий ещё не создан.";
  }
}

function renderFullRecapScriptStep() {
  const body = document.getElementById("stepBody");
  body.innerHTML = `
    <div class="settings-panel">
      <div class="settings-panel-title">🧠 Параметры пересказа</div>
      <div class="form-group">
        <label class="form-label">Текстовая модель</label>
        <input class="form-input" id="fullRecapTextModel" value="qwen2.5:14b" placeholder="Ollama model или ID модели 9router">
        <div class="text-xs text-dim mt-1">Сценарий создаётся по всем готовым кадрам и уже извлечённому контексту AniFlow. Дополнительного распознавания/вырезания изображений не будет.</div>
      </div>
      <div class="form-group">
        <label class="form-label">Целевой объём сценария</label>
        <select id="fullRecapTargetWords" class="form-select">
          <option value="5000" selected>5 000 слов — примерно 1 час</option>
          <option value="7500">7 500 слов — примерно 1 час 30 минут</option>
          <option value="10000">10 000 слов — примерно 2 часа</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Контекст истории (необязательно)</label>
        <textarea id="fullRecapStoryContext" class="form-input" rows="3" placeholder="Правильные имена, предыстория, термины или важные пояснения..."></textarea>
      </div>
      <div class="settings-panel" style="background:var(--bg-secondary);">
        <strong>Профиль повествования</strong>
        <p class="text-sm mt-1">Подробный последовательный пересказ с эмоциональной подачей, живым разговорным языком, уместной иронией и объяснением способностей, системы, мотивов и последствий. Реплики манги не копируются дословно — сюжет пересказывается авторским текстом.</p>
      </div>
    </div>
    <div class="settings-panel">
      <div class="settings-panel-title">📜 Сценарий</div>
      <textarea id="fullRecapScriptPreview" class="form-input" rows="12" readonly placeholder="После генерации здесь появится полный пересказ..."></textarea>
      <div id="fullRecapScriptMeta" class="text-xs text-dim mt-2">Сценарий ещё не создан.</div>
    </div>`;

  document.getElementById("stepActions").innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Назад</button>
    <div class="step-actions-right">
      <button class="btn btn-secondary" onclick="runFullRecapScript()">✍️ Создать пересказ</button>
      <button class="btn btn-primary" onclick="nextStep()">Проверить сценарий →</button>
    </div>`;

  loadFullRecapData().then(data => {
    if (!data) return;
    const model = document.getElementById("fullRecapTextModel");
    const words = document.getElementById("fullRecapTargetWords");
    const context = document.getElementById("fullRecapStoryContext");
    if (model && data.settings?.full_recap_text_model) model.value = data.settings.full_recap_text_model;
    if (words && data.settings?.full_recap_target_words) words.value = String(data.settings.full_recap_target_words);
    if (context && data.settings?.full_recap_story_context) context.value = data.settings.full_recap_story_context;
    renderFullRecapScriptPreview();
  });
}

async function runFullRecapScript() {
  const settings = {
    pipeline_mode: "full_recap",
    full_recap_text_model: document.getElementById("fullRecapTextModel")?.value.trim() || "qwen2.5:14b",
    full_recap_target_words: parseInt(document.getElementById("fullRecapTargetWords")?.value || "5000", 10),
    full_recap_story_context: document.getElementById("fullRecapStoryContext")?.value.trim() || "",
  };
  await startFullRecapStep("full_recap_script", settings);
}

function renderFullRecapReviewStep() {
  const body = document.getElementById("stepBody");
  body.innerHTML = `
    <p class="text-sm text-dim mb-2">Проверьте и отредактируйте пересказ. После сохранения приложение пересчитает количество слов и длительность немого видео по формуле 0,72 секунды на слово.</p>
    <div class="settings-panel">
      <div class="settings-panel-title">📝 Полный сценарий для озвучки вручную</div>
      <textarea id="fullRecapScriptEditor" class="form-input" rows="22" placeholder="Загружаю сценарий..."></textarea>
      <div id="fullRecapEditMeta" class="text-xs text-dim mt-2"></div>
    </div>`;

  document.getElementById("stepActions").innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Назад</button>
    <div class="step-actions-right">
      <button class="btn btn-secondary" onclick="saveFullRecapScript()">💾 Сохранить сценарий</button>
      <button class="btn btn-primary" onclick="nextStep()">К созданию видео →</button>
    </div>`;

  loadFullRecapData().then(data => {
    const editor = document.getElementById("fullRecapScriptEditor");
    if (editor) editor.value = data?.script || "";
    const meta = document.getElementById("fullRecapEditMeta");
    if (meta) meta.textContent = data?.script
      ? `${Number(data.word_count || 0).toLocaleString("ru-RU")} слов · ${formatRecapDuration(data.duration_seconds || 0)}`
      : "Сценарий пока не создан.";
  });
}

function formatRecapDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return `${String(hours).padStart(2,"0")}:${String(minutes).padStart(2,"0")}:${String(secs).padStart(2,"0")}`;
}

async function saveFullRecapScript() {
  const fullText = document.getElementById("fullRecapScriptEditor")?.value.trim() || "";
  if (!fullText) return toast("Сценарий пустой.", "error");
  try {
    const response = await fetch(`/api/full-recap/${encodeURIComponent(APP.projectName)}/script`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_text: fullText }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось сохранить сценарий");
    await loadFullRecapData();
    const meta = document.getElementById("fullRecapEditMeta");
    if (meta) meta.textContent = `${Number(data.word_count || 0).toLocaleString("ru-RU")} слов · ${formatRecapDuration(data.duration_seconds || 0)}`;
    toast("Сценарий сохранён. Длительность видео пересчитана.", "success");
  } catch (error) {
    toast("Ошибка сохранения: " + error.message, "error");
  }
}

function renderFullRecapVideoPreview() {
  const el = document.getElementById("fullRecapVideoPreview");
  if (!el || !FULL_RECAP_DATA?.video_path) return;
  el.innerHTML = `
    <div class="settings-panel">
      <div class="settings-panel-title">✅ Готовое видео без звука</div>
      <video controls preload="metadata" style="width:100%;max-height:520px;background:#000;border-radius:8px;" src="/api/full-recap/${encodeURIComponent(APP.projectName)}/video"></video>
      <div class="text-sm mt-2">${Number(FULL_RECAP_DATA.word_count || 0).toLocaleString("ru-RU")} слов · ${formatRecapDuration(FULL_RECAP_DATA.duration_seconds || 0)} · ${Number(FULL_RECAP_DATA.panel_count || 0).toLocaleString("ru-RU")} кадров</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
        <a class="btn btn-primary" href="/api/full-recap/${encodeURIComponent(APP.projectName)}/video" download>Скачать MP4</a>
        <a class="btn btn-secondary" href="/api/full-recap/${encodeURIComponent(APP.projectName)}/export" download>Скачать весь проект</a>
      </div>
    </div>`;
}

function renderFullRecapVideoStep() {
  document.getElementById("stepBody").innerHTML = `
    <div class="settings-panel">
      <div class="settings-panel-title">⏱️ Расчёт длительности</div>
      <div id="fullRecapDurationEstimate" class="text-lg">Загружаю сценарий…</div>
      <div class="text-xs text-dim mt-1">Формула: количество слов × 0,72 секунды. Все вырезанные кадры будут объединены по порядку с плавным движением. Аудиодорожки в видео не будет.</div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Разрешение YouTube</label>
        <select id="fullRecapResolution" class="form-select">
          <option value="1080p_landscape" selected>1920 × 1080</option>
          <option value="2k_landscape">2560 × 1440</option>
          <option value="4k_landscape">3840 × 2160</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Качество</label>
        <select id="fullRecapQuality" class="form-select">
          <option value="medium" selected>Обычное</option>
          <option value="high">Высокое</option>
        </select>
      </div>
    </div>
    <div id="fullRecapVideoPreview" class="mt-2"></div>
    <div class="progress-container hidden" id="fullVideoProgress">
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="fullVideoProgressBar"></div></div>
      <div class="progress-label"><span id="fullVideoProgressMsg">Рендеринг немого видео…</span><span class="pct" id="fullVideoProgressPct">0%</span></div>
    </div>`;
  document.getElementById("stepActions").innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Назад</button>
    <div class="step-actions-right">
      <button class="btn btn-primary" onclick="runFullRecapVideo()">🎬 Создать немое видео</button>
      <button class="btn btn-secondary" onclick="nextStep()">К оформлению →</button>
    </div>`;
  loadFullRecapData().then(data => {
    if (!data) return;
    const estimate = document.getElementById("fullRecapDurationEstimate");
    if (estimate) estimate.textContent = `${Number(data.word_count || 0).toLocaleString("ru-RU")} слов → ${formatRecapDuration(data.duration_seconds || 0)}`;
    const settings = data.settings || {};
    const resolution = document.getElementById("fullRecapResolution");
    const quality = document.getElementById("fullRecapQuality");
    if (resolution && settings.video_resolution) resolution.value = settings.video_resolution;
    if (quality && settings.video_quality) quality.value = settings.video_quality;
    if (data.video_path) renderFullRecapVideoPreview();
  });
}

async function runFullRecapVideo() {
  const settings = {
    pipeline_mode: "full_recap",
    video_resolution: document.getElementById("fullRecapResolution")?.value || "1080p_landscape",
    video_quality: document.getElementById("fullRecapQuality")?.value || "medium",
    video_fps: 30,
    animation_style: "auto",
  };
  await startFullRecapStep("full_recap_video", settings);
}

let FULL_RECAP_PACKAGE_DATA = null;

async function loadFullRecapPackageData() {
  if (!APP.projectName) return null;
  try {
    const response = await fetch(`/api/full-recap/${encodeURIComponent(APP.projectName)}/package`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось загрузить материалы оформления");
    FULL_RECAP_PACKAGE_DATA = data;
    return data;
  } catch (error) {
    console.error("[FullRecap] Package load failed:", error);
    return null;
  }
}

async function clearFullRecapReferences(kind) {
  if (!confirm("Удалить все сохранённые референсы этого типа для текущего проекта?")) return;
  try {
    const response = await fetch(
      `/api/full-recap/${encodeURIComponent(APP.projectName)}/references/${kind}`,
      { method: "DELETE" }
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось очистить референсы");
    await loadFullRecapPackageData();
    renderFullRecapPackagePreview();
    toast(`Удалено референсов: ${data.removed || 0}`, "success");
  } catch (error) {
    toast("Ошибка очистки: " + error.message, "error");
  }
}

async function uploadFullRecapReferences(kind, inputId) {
  const input = document.getElementById(inputId);
  const files = Array.from(input?.files || []);
  if (!files.length) return toast("Сначала выберите изображения.", "warning");
  const body = new FormData();
  files.forEach(file => body.append("files", file));
  try {
    const response = await fetch(`/api/full-recap/${encodeURIComponent(APP.projectName)}/references/${kind}`, {
      method: "POST", body,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Загрузка не удалась");
    toast(`Загружено референсов: ${data.files?.length || 0}`, "success");
    input.value = "";
    await loadFullRecapPackageData();
    renderFullRecapPackagePreview();
  } catch (error) {
    toast("Ошибка загрузки референсов: " + error.message, "error");
  }
}

function renderFullRecapPackagePreview() {
  const el = document.getElementById("fullRecapPackagePreview");
  if (!el) return;
  const data = FULL_RECAP_PACKAGE_DATA || {};
  const titles = data.titles || [];
  const thumbs = data.thumbnails || [];
  const thumbnailRefs = data.thumbnail_references || [];
  const titleRefs = data.title_references || [];
  el.innerHTML = `
    <div class="settings-panel">
      <div class="settings-panel-title">📌 Референсы этого выпуска</div>
      <div class="text-xs text-dim">Обложки: ${thumbnailRefs.length} · Названия: ${titleRefs.length}</div>
      <div class="text-xs text-dim mt-1">${thumbnailRefs.map(esc).join(", ") || "Референсы обложек не загружены"}<br>${titleRefs.map(esc).join(", ") || "Референсы названий не загружены"}</div>
    </div>
    ${titles.length ? `
      <div class="settings-panel">
        <div class="settings-panel-title">✍️ Три варианта названия</div>
        ${titles.map((item,index)=>`
          <label style="display:flex;gap:10px;align-items:flex-start;padding:12px;border:1px solid var(--border);border-radius:8px;margin:8px 0;cursor:pointer;">
            <input type="radio" name="fullRecapSelectedTitle" value="${index}" ${data.selected_title?.title === item.title ? "checked" : ""} onchange="selectFullRecapTitle(${index})" style="margin-top:4px;">
            <span style="flex:1;">
              <strong>${esc(item.title)}</strong>
              <span class="text-xs text-dim" style="display:block;margin-top:4px;">Надпись на обложке: ${esc(item.thumbnail_text || "")} · ${esc(item.angle || "")}</span>
            </span>
          </label>`).join("")}
      </div>` : ""}
    ${thumbs.length ? `
      <div class="settings-panel">
        <div class="settings-panel-title">🖼️ Три варианта обложки</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;">
          ${thumbs.map((item,index)=>`
            <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;">
              <img src="/api/full-recap/${encodeURIComponent(APP.projectName)}/thumbnails/${encodeURIComponent(item.filename)}" alt="Обложка ${index+1}" style="display:block;width:100%;aspect-ratio:16/9;object-fit:cover;">
              <div style="padding:10px;">
                <strong>Обложка ${index+1}</strong>
                <div class="text-xs text-dim">${esc(item.title || "")}</div>
                <a href="/api/full-recap/${encodeURIComponent(APP.projectName)}/thumbnails/${encodeURIComponent(item.filename)}" download style="font-size:12px;">Скачать JPG</a>
              </div>
            </div>`).join("")}
        </div>
      </div>` : ""}
    ${data.description ? `
      <div class="settings-panel">
        <div class="settings-panel-title">📝 Описание видео</div>
        <textarea id="fullRecapGeneratedDescription" class="form-input" rows="7" readonly>${esc(data.description)}</textarea>
        <button class="btn btn-secondary mt-2" onclick="copyFullRecapPackageText('description')">Скопировать описание</button>
      </div>` : ""}
    ${data.pinned_comment ? `
      <div class="settings-panel">
        <div class="settings-panel-title">📌 Закреплённый комментарий</div>
        <textarea id="fullRecapGeneratedPinnedComment" class="form-input" rows="4" readonly>${esc(data.pinned_comment)}</textarea>
        <button class="btn btn-secondary mt-2" onclick="copyFullRecapPackageText('pinned_comment')">Скопировать комментарий</button>
      </div>` : ""}
    ${data.status && data.status !== "ready" ? `<div class="text-xs text-dim mt-2">Статус: ${esc(data.status)}</div>` : ""}
  `;
}

async function copyFullRecapPackageText(kind) {
  const value = kind === "description"
    ? document.getElementById("fullRecapGeneratedDescription")?.value
    : document.getElementById("fullRecapGeneratedPinnedComment")?.value;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    toast("Текст скопирован.", "success");
  } catch (error) {
    toast("Не удалось скопировать. Выделите текст вручную.", "warning");
  }
}

async function selectFullRecapTitle(index) {
  try {
    const response = await fetch(`/api/full-recap/${encodeURIComponent(APP.projectName)}/package/selection`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось выбрать название");
    await loadFullRecapPackageData();
    toast("Название выбрано.", "success");
  } catch (error) {
    toast("Ошибка выбора названия: " + error.message, "error");
  }
}

function renderFullRecapPackageStep() {
  document.getElementById("stepBody").innerHTML = `
    <p class="text-sm text-dim mb-3">Встроенный стиль уже настроен по предоставленным примерам успешных каналов. Ничего загружать не обязательно. При желании можно добавить референсы именно этого выпуска — они будут дополнительными ориентирами, а не обязательным условием.</p>
    <div class="settings-panel">
      <div class="settings-panel-title">🖼️ Референсы обложек</div>
      <input id="fullRecapThumbnailRefs" type="file" accept="image/png,image/jpeg,image/webp" multiple class="form-input">
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
        <button class="btn btn-secondary" onclick="uploadFullRecapReferences('thumbnails','fullRecapThumbnailRefs')">Загрузить референсы обложек</button>
        <button class="btn btn-ghost" onclick="clearFullRecapReferences('thumbnails')">Очистить старые</button>
      </div>
      <div class="text-xs text-dim mt-1">Необязательно. До 16 PNG/JPG/WEBP; добавленные изображения уточняют стиль только этого выпуска.</div>
    </div>
    <div class="settings-panel">
      <div class="settings-panel-title">✍️ Референсы названий</div>
      <input id="fullRecapTitleRefs" type="file" accept="image/png,image/jpeg,image/webp" multiple class="form-input">
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
        <button class="btn btn-secondary" onclick="uploadFullRecapReferences('titles','fullRecapTitleRefs')">Загрузить скриншоты названий</button>
        <button class="btn btn-ghost" onclick="clearFullRecapReferences('titles')">Очистить старые</button>
      </div>
      <label class="form-label mt-3">Примеры названий текстом</label>
      <textarea id="fullRecapTitleReferenceText" class="form-input" rows="4" placeholder="Вставь сюда несколько названий, стиль которых нужно использовать как ориентир."></textarea>
      <div class="text-xs text-dim mt-1">Необязательно. Встроенный профиль названий используется автоматически; текстовые примеры могут дополнить его для этого выпуска.</div>
    </div>
    <div class="settings-panel">
      <div class="settings-panel-title">⚙️ Генерация превью</div>
      <label class="form-label">Модель</label>
      <select id="fullRecapImageModel" class="form-select">
        <option value="gpt-image-2.5-sunburst" selected>GPT Image 2.5 Sunburst — точнее работает с референсами</option>
        <option value="gpt-image-2.5-flare">GPT Image 2.5 Flare — быстрый вариант</option>
      </select>
      <div class="text-xs text-dim mt-1">Для создания трёх превью нужен OPENAI_API_KEY в локальном файле .env. Ключ не отправляется в браузер и не сохраняется в GitHub.</div>
    </div>
    <div id="fullRecapPackagePreview" class="mt-2"></div>`;
  document.getElementById("stepActions").innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-secondary" onclick="runFullRecapPackage()">✨ Сгенерировать 3 обложки и 3 названия</button>
      <button class="btn btn-primary" onclick="goHome()">Готово</button>
    </div>`;
  loadFullRecapPackageData().then(data => {
    if (!data) return;
    const select = document.getElementById("fullRecapImageModel");
    const text = document.getElementById("fullRecapTitleReferenceText");
    if (select && data.settings?.openai_image_model) select.value = data.settings.openai_image_model;
    if (text && data.settings?.full_recap_title_reference_text) text.value = data.settings.full_recap_title_reference_text;
    renderFullRecapPackagePreview();
  });
}

async function runFullRecapPackage() {
  const titleText = document.getElementById("fullRecapTitleReferenceText")?.value.trim() || "";
  const settings = {
    pipeline_mode: "full_recap",
    full_recap_title_reference_text: titleText,
    openai_image_model: document.getElementById("fullRecapImageModel")?.value || "gpt-image-2.5-sunburst",
  };
  await startFullRecapStep("full_recap_package", settings);
}

// ─── Step: Video ────────────────────────────────────────
function nextStep() {
  if (APP.currentStep < APP.steps.length - 1) {
    APP.currentStep++;
    renderWizard();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

function prevStep() {
  if (APP.currentStep > 0) {
    APP.currentStep--;
    renderWizard();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

// ─── Data Loading ───────────────────────────────────────
async function loadProjectData(name) {
  if (!name) return;
  try {
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}`);
    if (r.ok) {
      APP.projectData = await r.json();
      
      // DEBUG: Log received project data
      console.log('[DEBUG] loadProjectData received:', {
        manhwa_name: APP.projectData.manhwa_name,
        current_chapter: APP.projectData.current_chapter,
        is_batch: APP.projectData.is_batch,
        chapter_list: APP.projectData.chapter_list
      });
      
      // Update chapter navigation state from project data
      if (APP.projectData) {
        APP.manhwaName = APP.projectData.manhwa_name || '';
        APP.currentChapter = APP.projectData.current_chapter || 1;
        APP.isBatch = APP.projectData.is_batch || false;
        APP.chapterList = APP.projectData.chapter_list || [APP.currentChapter];

        // DEBUG: Log updated APP state
        console.log('[DEBUG] Updated APP state:', {
          manhwaName: APP.manhwaName,
          currentChapter: APP.currentChapter,
          isBatch: APP.isBatch,
          chapterList: APP.chapterList
        });

        // Re-render the chapter nav in place — step templates render it before
        // this fetch resolves, so the indicator would otherwise stay stale
        updateChapterNavUI();
      }
    }
  } catch (e) { 
    console.error('[DEBUG] loadProjectData error:', e);
  }
}

// ─── SocketIO Events ────────────────────────────────────
socket.on('connect', () => { console.log('[WS] Connected'); });

socket.on('progress', (data) => {
  updateProgress(data);
});

socket.on('step_started', (data) => {
  console.log('[WS] Step started:', data.step);
  setRunning(true, `Running ${data.step}...`);
});

socket.on('step_complete', (data) => {
  console.log('[WS] Step complete:', data.step, data.error);
  setRunning(false);

  // During a full batch run the overlay handles the UI — no auto-advance
  if (APP.batchRunning) return;

  if (data.error) {
    toast(`Error in ${data.step}: ${data.error}`, 'error');
    return;
  }

  toast(`${data.step} completed!`, 'success');

  // Reload project data
  loadProjectData(APP.projectName);

  if (String(data.step || '').startsWith('full_recap_')) {
    loadFullRecapData().then(() => {
      if (data.step === 'full_recap_script') renderFullRecapScriptPreview();
      if (data.step === 'full_recap_video') renderFullRecapVideoPreview();
      if (data.step === 'full_recap_package') loadFullRecapPackageData().then(() => renderFullRecapPackagePreview());
    });
    return;
  }

  // Auto-advance or enable buttons based on step
  const step = data.step;
  if (step === 'load') {
    nextStep();
  } else if (step === 'stitch') {
    enable('btnDetect');
    toast('Pages stitched! Now detect panels.', 'info');
    // Reload project data then show stitched preview
    loadProjectData(APP.projectName).then(() => { loadStitchedPreview(); });
  } else if (step === 'detect1' || step === 'detect') {
    enable('btnCrop');
    toast('Panels detected! Review boxes or crop them.', 'info');
    // Reload project data to get detection boxes, then refresh overlay
    loadProjectData(APP.projectName).then(() => { loadStitchedPreview(); });
  } else if (step === 'crop1' || step === 'crop') {
    if (APP.mode === 'narrated' || APP.mode === 'full_recap') {
      enable('btnStitch2');
      toast('Bubble panels cropped! Now run Stitch 2 to combine them.', 'info');
    } else {
      enable('btnStitchNext');
      toast('Panels cropped! Click Continue to review.', 'info');
    }
  } else if (step === 'stitch2') {
    enable('btnDetect2');
    toast('Panels re-stitched! Now detect art panels.', 'info');
    loadProjectData(APP.projectName).then(() => { loadStitched2Preview(); });
  } else if (step === 'detect2') {
    enable('btnCrop2');
    toast('Art panels detected! Review boxes or crop them.', 'info');
    loadProjectData(APP.projectName).then(() => { loadStitched2Preview(); });
  } else if (step === 'crop2') {
    enable('btnStitchNext');
    toast('Art panels cropped! Click Continue to review.', 'info');
  } else if (step === 'extract_dialogue' || step === 'extract_text') {
    // Refresh preview
    loadProjectData(APP.projectName).then(() => {
      if (APP.projectData) {
        const pwt = APP.projectData.panels_with_text || APP.projectData.panels || [];
        renderExtractedTexts(pwt);
      }
    });
  } else if (step === 'narrate') {
    loadProjectData(APP.projectName).then(() => {
      if (APP.projectData) renderNarrationPreview(APP.projectData.panels);
    });
  } else if (step === 'video') {
    // Auto-advance to review clips step when clips are generated
    toast('Clips generated successfully! Advancing to review...', 'success');
    setTimeout(() => {
      nextStep();
    }, 1000);
  }
});

socket.on('pipeline_complete', (data) => {
  setRunning(false);
  if (data.error) {
    toast('Pipeline error: ' + data.error, 'error');
  } else {
    toast('Pipeline complete!', 'success');
  }
});

// ─── 🚀 Full Batch socket events ─────────────────────────
socket.on('batch_pipeline_started', (data) => {
  console.log('[WS] Full batch started:', data.project, data.steps);
  updateBatchOverlay(null, `${data.total_chapters} chapter(s) queued`, 0);
});

socket.on('batch_step_started', (data) => {
  updateBatchOverlay(data.step, null, 0);
});

// Reuse the generic progress stream: during a batch it carries per-chapter
// messages like "Processing Chapter 3 (3/89)..."
const _origUpdateProgress = updateProgress;
updateProgress = function (data) {
  if (APP.batchRunning) {
    const m = /Processing Chapter (\d+) \((\d+)\/(\d+)\)/.exec(data.message || '');
    if (m) {
      updateBatchOverlay(null,
        `Chapter ${m[1]} — ${Math.round(data.percent || 0)}% through this step (${m[2]}/${m[3]})`,
        data.percent || 0);
    } else if (data.message) {
      updateBatchOverlay(null, data.message, data.percent || 0);
    }
    return;
  }
  _origUpdateProgress(data);
};

socket.on('batch_pipeline_complete', (data) => {
  APP.batchRunning = false;
  hideBatchOverlay();
  if (data.error) {
    toast(`❌ Batch failed: ${data.error}`, 'error');
    playDoneBeep();
    return;
  }
  const chapters = data.chapters || [];
  const ready = data.clips_ready !== undefined ? data.clips_ready
    : chapters.filter(c => c.stage === 'clips_done' || c.stage === 'video_done').length;
  const failed = chapters.filter(c => c.error);
  toast(`🎉 Batch complete — ${ready}/${chapters.length} chapters ready for review`, 'success');
  playDoneBeep();
  if (failed.length) {
    toast(`⚠️ ${failed.length} chapter(s) reported errors — check the dashboard`, 'warning');
  }
  if (data.cancelled) {
    // Cancelled runs keep the user where they are — just refresh data
    loadProjectData(APP.projectName);
    return;
  }
  // ✅ Full batch = everything through clip generation → land on Review Clips
  openWizardAtStep(APP.projectName, 'review_clips');
});

// ─── Progress Handling ──────────────────────────────────
function updateProgress(data) {
  const pct = data.percent || 0;
  const msg = data.message || 'Processing...';

  // Try to find the active progress bar
  const prefixes = ['download', 'stitch', 'extract', 'fullRecap', 'fullVideo'];
  for (const p of prefixes) {
    const bar = document.getElementById(`${p}ProgressBar`);
    const msgEl = document.getElementById(`${p}ProgressMsg`);
    const pctEl = document.getElementById(`${p}ProgressPct`);
    const container = document.getElementById(`${p}Progress`);

    if (bar && container) {
      container.classList.remove('hidden');
      bar.style.width = pct + '%';
      if (msgEl) msgEl.textContent = msg;
      if (pctEl) pctEl.textContent = pct + '%';
    }
  }
}

function showProgress(prefix) {
  const container = document.getElementById(`${prefix}Progress`);
  if (container) container.classList.remove('hidden');
}

// ─── UI Helpers ─────────────────────────────────────────
function setRunning(isRunning, message) {
  APP.running = isRunning;
  // Could add a global running indicator here if needed
}

function enable(id) {
  const el = document.getElementById(id);
  if (el) el.disabled = false;
}

function disable(id) {
  const el = document.getElementById(id);
  if (el) el.disabled = true;
}

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ─── Toast ──────────────────────────────────────────────
function toast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = message;
  container.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ─── Modal ──────────────────────────────────────────────
function openModal(title, bodyHtml, actionsHtml) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = bodyHtml;
  document.getElementById('modalActions').innerHTML = actionsHtml || '';
  document.getElementById('modalOverlay').classList.remove('hidden');
}

function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('modalOverlay').classList.add('hidden');
}


// ─── Step: Sort Clips ────────────────────────────────────────────
let sortJobs = []; // Track sorting jobs: {id, outputFolder, startChapter, endChapter, status, completed}

function renderSortClipsStep() {
  const body = document.getElementById('stepBody');
  body.innerHTML = `
    <div id="chapterNavSlot">${renderChapterNavigation()}</div>
    
    <p class="text-sm text-dim mb-3">
      Organize clips from multiple chapters into sequential folders for easier editing in CapCut or other video editors.
    </p>
    
    <div class="sort-clips-container" style="display: flex; flex-direction: column; gap: 20px;">
      <!-- Add New Sort Job -->
      <div class="card" style="padding: 20px; background: var(--bg-secondary); border-radius: 12px;">
        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary);">
          📂 Create New Sort Job
        </h3>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
          <div>
            <label class="text-xs text-dim" style="display: block; margin-bottom: 6px;">Output Folder</label>
            <input 
              type="text" 
              id="sortOutputFolder" 
              placeholder="e.g., /path/to/output/batch1"
              style="width: 100%; padding: 10px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary);">
            <button 
              class="btn btn-sm btn-ghost" 
              onclick="browseFolderForSort()"
              style="margin-top: 6px; font-size: 12px;">
              📁 Browse...
            </button>
          </div>
          
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div>
              <label class="text-xs text-dim" style="display: block; margin-bottom: 6px;">Start Chapter</label>
              <input 
                type="number" 
                id="sortStartChapter" 
                min="1" 
                value="1"
                placeholder="1"
                style="width: 100%; padding: 10px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary);">
            </div>
            <div>
              <label class="text-xs text-dim" style="display: block; margin-bottom: 6px;">End Chapter</label>
              <input 
                type="number" 
                id="sortEndChapter" 
                min="1" 
                value="5"
                placeholder="5"
                style="width: 100%; padding: 10px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary);">
            </div>
          </div>
        </div>
        
        <button 
          class="btn btn-primary" 
          onclick="addSortJob()"
          style="width: 100%;">
          ➕ Add Sort Job
        </button>
      </div>
      
      <!-- Sort Jobs List -->
      <div id="sortJobsList"></div>
    </div>
  `;

  const actions = document.getElementById('stepActions');
  actions.innerHTML = `
    <button class="btn btn-ghost" onclick="prevStep()">← Back</button>
    <div class="step-actions-right">
      <button class="btn btn-primary" onclick="finishProject()">✓ Done — Back to Home</button>
    </div>`;

  renderSortJobsList();
}
window.renderSortClipsStep = renderSortClipsStep;

function finishProject() {
  toast('🎉 Project complete! Clips are sorted and ready.', 'success');
  goHome();
}

function browseFolderForSort() {
  // Use backend API to get a folder path via system dialog
  toast('Opening folder picker...', 'info');
  
  fetch('/api/browse-folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Select Output Folder for Sorted Clips' })
  })
  .then(response => response.json())
  .then(data => {
    if (data.path) {
      document.getElementById('sortOutputFolder').value = data.path;
      toast('✓ Folder selected', 'success');
    } else if (data.cancelled) {
      toast('Folder selection cancelled', 'info');
    } else if (data.error) {
      toast('Error: ' + data.error, 'error');
    }
  })
  .catch(error => {
    // Fallback: use text input
    toast('Folder picker not available. Please enter path manually.', 'warning');
  });
}

function addSortJob() {
  const outputFolder = document.getElementById('sortOutputFolder').value.trim();
  const startChapter = parseInt(document.getElementById('sortStartChapter').value);
  const endChapter = parseInt(document.getElementById('sortEndChapter').value);
  
  if (!outputFolder) {
    toast('Please enter an output folder path', 'warning');
    return;
  }
  
  if (startChapter > endChapter) {
    toast('Start chapter must be less than or equal to end chapter', 'warning');
    return;
  }
  
  // Check if range already exists in a job
  const overlap = sortJobs.find(j => 
    (startChapter >= j.startChapter && startChapter <= j.endChapter) ||
    (endChapter >= j.startChapter && endChapter <= j.endChapter)
  );
  
  if (overlap) {
    toast(`Chapter range ${startChapter}-${endChapter} overlaps with existing job (${overlap.startChapter}-${overlap.endChapter})`, 'warning');
    return;
  }
  
  const job = {
    id: Date.now(),
    outputFolder,
    startChapter,
    endChapter,
    status: 'pending',
    completed: false,
    progress: 0,
    totalClips: 0,
    copiedClips: 0
  };
  
  sortJobs.push(job);
  toast(`✅ Added sort job: Chapters ${startChapter}-${endChapter}`, 'success');
  
  // Clear inputs
  document.getElementById('sortOutputFolder').value = '';
  document.getElementById('sortStartChapter').value = endChapter + 1;
  document.getElementById('sortEndChapter').value = endChapter + 5;
  
  renderSortJobsList();
}

function renderSortJobsList() {
  const container = document.getElementById('sortJobsList');
  
  if (sortJobs.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <div class="empty-state-text">No sort jobs yet. Create one above to organize your clips.</div>
      </div>`;
    return;
  }
  
  container.innerHTML = sortJobs.map(job => `
    <div class="card" style="padding: 20px; background: var(--bg-secondary); border-radius: 12px; border-left: 4px solid ${job.completed ? 'var(--color-success)' : job.status === 'running' ? 'var(--color-warning)' : 'var(--border)'};">
      <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
        <div>
          <div style="font-weight: 600; font-size: 15px; margin-bottom: 4px;">
            ${job.completed ? '✓' : job.status === 'running' ? '⏳' : '📋'} 
            Chapters ${job.startChapter} - ${job.endChapter}
          </div>
          <div class="text-xs text-dim">
            Output: ${job.outputFolder}
          </div>
        </div>
        <div style="display: flex; gap: 8px;">
          ${!job.completed && job.status !== 'running' ? `
            <button 
              class="btn btn-sm btn-primary" 
              onclick="executeSortJob(${job.id})"
              title="Start sorting">
              ▶ Start
            </button>
          ` : ''}
          ${job.status !== 'running' ? `
            <button 
              class="btn btn-sm btn-ghost" 
              onclick="removeSortJob(${job.id})"
              title="Remove job">
              🗑️
            </button>
          ` : ''}
        </div>
      </div>
      
      ${job.status === 'running' || job.completed ? `
        <div style="background: var(--bg-primary); border-radius: 6px; padding: 12px; margin-top: 12px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span class="text-xs text-dim">Progress</span>
            <span class="text-xs" style="font-weight: 600;">${job.copiedClips} / ${job.totalClips} clips</span>
          </div>
          <div style="height: 6px; background: var(--bg-secondary); border-radius: 3px; overflow: hidden;">
            <div style="height: 100%; background: var(--color-success); width: ${job.progress}%; transition: width 0.3s;"></div>
          </div>
        </div>
      ` : ''}
    </div>
  `).join('');
}

function removeSortJob(jobId) {
  sortJobs = sortJobs.filter(j => j.id !== jobId);
  toast('Sort job removed', 'success');
  renderSortJobsList();
}

async function executeSortJob(jobId) {
  const job = sortJobs.find(j => j.id === jobId);
  if (!job) return;
  
  job.status = 'running';
  job.progress = 0;
  renderSortJobsList();
  
  try {
    const response = await fetch('/api/sort-clips', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        output_folder: job.outputFolder,
        start_chapter: job.startChapter,
        end_chapter: job.endChapter
      })
    });
    
    const data = await response.json();
    
    if (response.ok) {
      job.completed = true;
      job.status = 'completed';
      job.progress = 100;
      job.totalClips = data.total_clips;
      job.copiedClips = data.copied_clips;
      toast(`✅ Sorted ${data.copied_clips} clips from chapters ${job.startChapter}-${job.endChapter}`, 'success');
      
      // Auto-advance progress for visual feedback
      let progressStep = 0;
      const progressInterval = setInterval(() => {
        if (progressStep < 100) {
          progressStep += 10;
          job.progress = progressStep;
          renderSortJobsList();
        } else {
          clearInterval(progressInterval);
        }
      }, 50);
    } else {
      job.status = 'error';
      toast(`❌ Sort failed: ${data.error}`, 'error');
    }
  } catch (error) {
    job.status = 'error';
    toast(`❌ Sort failed: ${error.message}`, 'error');
  }
  
  renderSortJobsList();
}

// ─── Chapter Navigation ──────────────────────────────────
function updateChapterNavUI() {
  // Re-render the chapter nav inside its slot — works whether the slot was
  // rendered empty (data hadn't arrived yet) or already holds the nav
  const slot = document.getElementById('chapterNavSlot');
  if (!slot) return;
  slot.innerHTML = renderChapterNavigation();
}

function renderChapterNavigation() {
  // DEBUG: Log current state
  console.log('[DEBUG] renderChapterNavigation called');
  console.log('[DEBUG] APP.userBatchMode:', APP.userBatchMode);
  console.log('[DEBUG] APP.isBatch:', APP.isBatch);
  console.log('[DEBUG] APP.chapterList:', APP.chapterList);
  console.log('[DEBUG] APP.chapterList.length:', APP.chapterList?.length);
  console.log('[DEBUG] APP.currentChapter:', APP.currentChapter);
  console.log('[DEBUG] APP.manhwaName:', APP.manhwaName);
  
  // Show navigation if:
  // 1. User explicitly enabled batch mode (userBatchMode = true), OR
  // 2. Backend detected batch mode (isBatch = true) AND we have multiple chapters
  const shouldShowNav = APP.userBatchMode || (APP.isBatch && APP.chapterList.length > 1);
  
  if (!shouldShowNav) {
    console.log('[DEBUG] No navigation - userBatchMode:', APP.userBatchMode, 'isBatch:', APP.isBatch, 'chapterCount:', APP.chapterList?.length);
    return ''; // No navigation needed
  }
  
  // Clamp the index — a stale current_chapter (e.g. 0) may not be in the list
  const idx = APP.chapterList.indexOf(APP.currentChapter);
  const currentIdx = idx >= 0 ? idx : 0;
  const displayChapter = idx >= 0 ? APP.currentChapter : (APP.chapterList[0] ?? APP.currentChapter);
  const hasPrev = idx > 0;
  const hasNext = idx >= 0 ? idx < APP.chapterList.length - 1 : APP.chapterList.length > 0;

  return `
    <div class="chapter-nav">
      <button class="btn-chapter-nav" onclick="switchChapter('prev')"
              ${!hasPrev ? 'disabled' : ''}>
        <span>←</span> Previous
      </button>
      <div class="chapter-indicator">
        <strong>${APP.manhwaName}</strong><br>
        <span>Chapter ${String(displayChapter).padStart(5, '0')}</span>
        <span style="opacity: 0.6; font-size: 0.9em;"> (${currentIdx + 1}/${APP.chapterList.length})</span>
      </div>
      <button class="btn-chapter-nav" onclick="switchChapter('next')"
              ${!hasNext ? 'disabled' : ''}>
        Next <span>→</span>
      </button>
    </div>
  `;
}

async function switchChapter(direction) {
  if (APP.running) {
    toast('Cannot switch chapters while a step is running', 'warning');
    return;
  }
  
  const currentIdx = APP.chapterList.indexOf(APP.currentChapter);
  let newIdx = currentIdx;
  
  if (direction === 'prev' && currentIdx > 0) {
    newIdx = currentIdx - 1;
  } else if (direction === 'next' && currentIdx < APP.chapterList.length - 1) {
    newIdx = currentIdx + 1;
  } else {
    return; // No change
  }
  
  const newChapter = APP.chapterList[newIdx];
  
  try {
    // Call backend to switch chapter in state
    const resp = await fetch('/api/switch-chapter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_name: APP.projectName,
        chapter_num: newChapter
      })
    });
    
    if (!resp.ok) {
      const err = await resp.json();
      toast(`Failed to switch chapter: ${err.error}`, 'error');
      return;
    }
    
    // Get updated chapter state from response
    const data = await resp.json();
    
    // Update APP state with new chapter data
    APP.currentChapter = data.current_chapter;
    APP.manhwaName = data.manhwa_name;
    if (data.chapter_list) APP.chapterList = data.chapter_list;
    if (typeof data.is_batch === 'boolean') APP.isBatch = data.is_batch;
    if (data.stage) APP.projectData.stage = data.stage;
    if (data.panels) APP.projectData.panels = data.panels;
    if (data.panels_with_text) APP.projectData.panels_with_text = data.panels_with_text;
    if (data.stitched_parts) APP.projectData.stitched_parts = data.stitched_parts;
    if (data.stitched_boxes) APP.projectData.stitched_boxes = data.stitched_boxes;

    // Clear stale per-chapter viewer state so boxes drawn on the previous
    // chapter's stitched image don't linger on the new one
    stitchBoxes = [];

    // Reload full project data to ensure consistency
    await loadProjectData(APP.projectName);
    
    // Re-render current step with new chapter data
    renderStepContent();
    
    // If on stitch step, reload stitched preview
    if (APP.currentStep === 'stitch') {
      loadStitchedPreview();
    }
    
    // If on review step, reload panels
    if (APP.currentStep === 'review') {
      loadPanelReview();
    }
    
    toast(`Switched to Chapter ${String(newChapter).padStart(5, '0')}`, 'success');
  } catch (error) {
    toast(`Error switching chapter: ${error.message}`, 'error');
  }
}
