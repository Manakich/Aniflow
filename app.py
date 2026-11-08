"""
AniFlow - Automated Manhwa Video Creation
Full-featured Flask app with all pipeline controls.
"""
import os, json, threading, shutil, re, sys

# Load local API keys without ever committing them to the repository.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

# Line-buffer stdout/stderr so redirected logs (server.log) update live
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
from flask import (Flask, render_template, request, jsonify, send_from_directory, send_file)
from flask_socketio import SocketIO, emit
import config
from pipeline.orchestrator import Orchestrator, PipelineState
from pipeline.cast_system import Cast, list_casts
from pipeline.panel_extractor_yolo import get_global_extractor, get_global_bubble_extractor
from pipeline.web_scraper import analyze_url, download_chapters, list_downloaded_manga, get_download_root
from pipeline import character_builder as charbuilder

app = Flask(__name__)
# Re-read templates from disk on every request so HTML edits (e.g. logo
# changes) show up without a server restart — Jinja caches compiled
# templates when debug is off, which made stale headers stick around
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'aniflow-dev-key')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB upload limit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
orchestrator = Orchestrator()
pipeline_thread = None

def progress_callback(stage, current, total, message):
    socketio.emit('progress', {'stage': stage, 'current': current, 'total': total,
                               'message': message, 'percent': int((current / max(total, 1)) * 100)})

orchestrator.add_progress_callback(progress_callback)

# ─── Page Routes ─────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

# ─── API Routes ──────────────────────────────────────────────────
@app.route('/api/status', methods=['GET'])
def get_status():
    deps = orchestrator.check_dependencies()
    return jsonify(deps)

@app.route('/api/projects', methods=['GET'])
def list_projects():
    return jsonify(orchestrator.get_projects())

@app.route('/api/projects/<name>', methods=['GET'])
def get_project(name):
    state = PipelineState.load(name)
    
    # IMMEDIATE FIX: Detect batch mode manually by checking folder structure
    # This bypasses the broken state loading logic
    # NOTE: use state.project_name (resolved to the real on-disk folder) —
    # the request name may be a display name like "Nan Hao Shang Feng"
    project_root = os.path.join(config.MANHWA_DOWNLOAD_DIR, state.project_name)  # resolved name
    manual_batch_check = False
    manual_chapter_list = [state.current_chapter]
    
    # DEBUG: Log exactly what we're checking
    print(f"[DEBUG] Checking path: {project_root}")
    print(f"[DEBUG] Path exists: {os.path.exists(project_root)}")
    if os.path.exists(project_root):
        all_items = os.listdir(project_root)
        print(f"[DEBUG] Contents: {all_items}")
        
        # Find Chapter_ folders that have actual images (not empty)
        chapter_dirs = []
        for d in all_items:
            if os.path.isdir(os.path.join(project_root, d)) and d.startswith('Chapter_'):
                chapter_path = os.path.join(project_root, d)
                # Check if chapter has images
                has_images = any(
                    f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                    for f in os.listdir(chapter_path)
                )
                if has_images:
                    chapter_dirs.append(d)
        
        print(f"[DEBUG] Chapter dirs with images: {chapter_dirs}")
        if len(chapter_dirs) > 1:
            manual_batch_check = True
            manual_chapter_list = sorted([
                int(d.replace('Chapter_', '')) for d in chapter_dirs
            ])
            print(f"[MANUAL BATCH FIX] ✅ Found {len(chapter_dirs)} chapters: {manual_chapter_list}")
        else:
            print(f"[DEBUG] Only {len(chapter_dirs)} chapter dirs found, not batch mode")
    else:
        print(f"[DEBUG] Project root doesn't exist")
    
    # Override state values with manual detection
    actual_is_batch = manual_batch_check
    actual_chapter_list = manual_chapter_list
    actual_manhwa_name = state.project_name.replace('-', ' ').replace('Dragonslayers', "Dragonslayer's")  # Fix display name
    
    return jsonify({
        'name': state.project_name, 'stage': state.stage, 'panels': state.panels,
        'raw_pages': [os.path.basename(p) for p in state.raw_pages],
        'stitched_parts': state.stitched_parts,
        'stitched_boxes': state.stitched_boxes,
        'stitched_boxes_1': state.stitched_boxes_1,
        'stitched_boxes_2': state.stitched_boxes_2,
        'stitched_parts_2': state.stitched_parts_2,
        'panels_with_text': state.panels_with_text,
        'panels_mapping': state.panels_mapping,
        'error': state.error, 'video_path': state.video_path,
        'settings': state.settings, 'created_at': state.created_at, 'updated_at': state.updated_at,
        # Chapter navigation info - USE MANUAL DETECTION
        'manhwa_name': actual_manhwa_name,
        'current_chapter': state.current_chapter,
        'is_batch': actual_is_batch,
        'chapter_list': actual_chapter_list,
    })

@app.route('/api/projects/<name>', methods=['DELETE'])
def delete_project(name):
    orchestrator.delete_project(name)
    return jsonify({'status': 'deleted'})

@app.route('/api/projects/<name>/settings', methods=['POST'])
def update_settings(name):
    state = PipelineState.load(name)
    state.settings.update(request.json)
    state.save()
    return jsonify({'status': 'updated', 'settings': state.settings})

@app.route('/api/hardware', methods=['GET'])
def hardware_info():
    """Hardware info so the Speed Mode panel can suggest sensible defaults."""
    import platform as _platform
    videotoolbox = False
    try:
        from pipeline.compositor import _probe_videotoolbox
        videotoolbox = _probe_videotoolbox(30)
    except Exception:
        videotoolbox = False
    return jsonify({
        'cpu_count': os.cpu_count() or 4,
        'platform': _platform.system(),
        'videotoolbox': videotoolbox,
    })

@app.route('/api/switch-chapter', methods=['POST'])
def switch_chapter():
    """Switch to a different chapter in batch processing."""
    data = request.json
    project_name = data.get('project_name')
    chapter_num = data.get('chapter_num')
    
    if not project_name or chapter_num is None:
        return jsonify({'error': 'project_name and chapter_num required'}), 400
    
    try:
        state = PipelineState.load(project_name)

        # MANUAL BATCH CHECK (same as get_project endpoint) — use the resolved
        # project name so display names with spaces still find the real folder
        project_root = os.path.join(config.MANHWA_DOWNLOAD_DIR, state.project_name)
        manual_batch_check = False
        manual_chapter_list = [state.current_chapter]
        
        if os.path.exists(project_root):
            # Find Chapter_ folders that have actual images (not empty)
            chapter_dirs = []
            for d in os.listdir(project_root):
                if os.path.isdir(os.path.join(project_root, d)) and d.startswith('Chapter_'):
                    chapter_path = os.path.join(project_root, d)
                    # Check if chapter has images
                    has_images = any(
                        f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                        for f in os.listdir(chapter_path)
                    )
                    if has_images:
                        chapter_dirs.append(d)
            
            if len(chapter_dirs) > 1:
                manual_batch_check = True
                manual_chapter_list = sorted([
                    int(d.replace('Chapter_', '')) for d in chapter_dirs
                ])
        
        # Use manual batch detection
        if not manual_batch_check:
            return jsonify({'error': 'Project is not a batch project'}), 400
        
        if chapter_num not in manual_chapter_list:
            return jsonify({'error': f'Chapter {chapter_num} not in chapter list'}), 400
        
        # Update state's chapter list with manual detection before switching
        state.is_batch = manual_batch_check
        state.chapter_list = manual_chapter_list
        
        state.switch_to_chapter(chapter_num)
        state.save()
        
        # Return full chapter state so frontend can update UI
        return jsonify({
            'status': 'switched',
            'current_chapter': state.current_chapter,
            'manhwa_name': state.manhwa_name,
            'chapter_list': state.chapter_list,
            'is_batch': state.is_batch,
            'stage': state.stage,
            'panels': state.panels,
            'panels_with_text': state.panels_with_text,
            'stitched_parts': state.stitched_parts,
            'stitched_boxes': state.stitched_boxes,
            'error': state.error,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse-folder', methods=['POST'])
def browse_folder():
    """Open native folder picker dialog."""
    try:
        import platform
        import subprocess
        
        if platform.system() == 'Darwin':  # macOS
            # Use AppleScript for folder picker on macOS
            script = '''
            tell application "System Events"
                activate
                set folderPath to choose folder with prompt "Select Output Folder for Sorted Clips"
                return POSIX path of folderPath
            end tell
            '''
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                folder_path = result.stdout.strip()
                if folder_path:
                    return jsonify({'path': folder_path})
                else:
                    return jsonify({'cancelled': True}), 200
            elif 'User canceled' in result.stderr:
                return jsonify({'cancelled': True}), 200
            else:
                return jsonify({'error': 'Folder selection failed'}), 400
        else:
            # Use tkinter for other platforms
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            folder_path = filedialog.askdirectory(
                title='Select Output Folder for Sorted Clips',
                mustexist=True
            )
            
            root.destroy()
            
            if folder_path:
                return jsonify({'path': folder_path})
            else:
                return jsonify({'cancelled': True}), 200
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Folder selection timeout'}), 500
    except ImportError:
        return jsonify({'error': 'tkinter not available - please enter path manually'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/full-recap/<project_name>', methods=['GET'])
def get_full_recap(project_name):
    """Return script, numbered-panel metadata, silent video and YouTube package."""
    state = PipelineState.load(project_name)
    panels = state.full_recap_panels or state.panels
    return jsonify({
        'status': state.full_recap_status,
        'script': state.full_recap_script,
        'word_count': state.full_recap_word_count,
        'duration_seconds': state.full_recap_duration_seconds,
        'video_path': state.full_recap_video_path,
        'export_dir': state.full_recap_export_dir,
        'panel_count': len(panels),
        'panels': [
            {
                'panel_id': panel.get('panel_id'),
                'sequence_number': panel.get('sequence_number', index),
                'source_chapter': panel.get('source_chapter'),
            }
            for index, panel in enumerate(panels, start=1)
        ],
        'titles': state.full_recap_titles,
        'selected_title': state.full_recap_selected_title,
        'thumbnails': [
            {key: value for key, value in item.items() if key != 'path'}
            for item in state.full_recap_thumbnails
        ],
        'description': state.full_recap_description,
        'pinned_comment': state.full_recap_pinned_comment,
        'package_status': state.full_recap_package_status,
        'settings': {
            'full_recap_text_model': state.settings.get('full_recap_text_model', ''),
            'full_recap_style': state.settings.get('full_recap_style', ''),
            'full_recap_target_words': state.settings.get('full_recap_target_words', 5000),
            'video_resolution': state.settings.get('video_resolution', '1080p_landscape'),
            'animation_style': state.settings.get('animation_style', 'auto'),
        },
    })


@app.route('/api/full-recap/<project_name>/references/<kind>', methods=['POST'])
def upload_full_recap_references(project_name, kind):
    """Upload separate visual-style or title-style reference screenshots."""
    if kind not in ('thumbnails', 'titles'):
        return jsonify({'error': 'Reference type must be thumbnails or titles'}), 400
    try:
        from pipeline.full_recap_media import save_reference_uploads
        state = PipelineState.load(project_name)
        uploads = request.files.getlist('files')
        if not uploads:
            return jsonify({'error': 'Выберите хотя бы один файл'}), 400
        saved = save_reference_uploads(state.full_recap_workspace_dir or state.project_dir, kind, uploads)
        state.full_recap_package_status = 'references_updated'
        state.save()
        return jsonify({
            'status': 'uploaded',
            'kind': kind,
            'files': [{'filename': item['filename'], 'name': item['name']} for item in saved],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/full-recap/<project_name>/references/<kind>', methods=['DELETE'])
def clear_full_recap_references(project_name, kind):
    """Clear one reference set before preparing a different video."""
    if kind not in ('thumbnails', 'titles'):
        return jsonify({'error': 'Reference type must be thumbnails or titles'}), 400
    try:
        from pipeline.full_recap_media import clear_reference_files
        state = PipelineState.load(project_name)
        removed = clear_reference_files(
            state.full_recap_workspace_dir or state.project_dir, kind
        )
        state.full_recap_package_status = 'references_updated'
        state.save()
        return jsonify({'status': 'cleared', 'kind': kind, 'removed': removed})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/full-recap/<project_name>/package', methods=['GET'])
def get_full_recap_package(project_name):
    """Return generated metadata and uploaded reference filenames."""
    try:
        from pipeline.full_recap_media import list_reference_files
        state = PipelineState.load(project_name)
        return jsonify({
            'status': state.full_recap_package_status,
            'titles': state.full_recap_titles,
            'selected_title': state.full_recap_selected_title,
            'description': state.full_recap_description,
            'pinned_comment': state.full_recap_pinned_comment,
            'thumbnails': [
                {key: value for key, value in item.items() if key != 'path'}
                for item in state.full_recap_thumbnails
            ],
            'thumbnail_references': [
                item['filename'] for item in list_reference_files(state.full_recap_workspace_dir or state.project_dir, 'thumbnails')
            ],
            'title_references': [
                item['filename'] for item in list_reference_files(state.full_recap_workspace_dir or state.project_dir, 'titles')
            ],
            'settings': {
                'openai_image_model': state.settings.get('openai_image_model', 'gpt-image-2'),
                'full_recap_title_reference_text': state.settings.get('full_recap_title_reference_text', ''),
            },
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/full-recap/<project_name>/package/selection', methods=['PUT'])
def select_full_recap_title(project_name):
    data = request.get_json(silent=True) or {}
    selected = data.get('index')
    state = PipelineState.load(project_name)
    try:
        selected = int(selected)
    except (TypeError, ValueError):
        return jsonify({'error': 'Номер варианта должен быть числом'}), 400
    if selected < 0 or selected >= len(state.full_recap_titles):
        return jsonify({'error': 'Такого варианта названия нет'}), 400
    state.full_recap_selected_title = state.full_recap_titles[selected]
    workspace = state.full_recap_workspace_dir or state.project_dir
    package_dir = os.path.join(workspace, 'full_recap')
    os.makedirs(package_dir, exist_ok=True)
    package = {
        'titles': state.full_recap_titles,
        'selected_title': state.full_recap_selected_title,
        'description': state.full_recap_description,
        'pinned_comment': state.full_recap_pinned_comment,
    }
    with open(os.path.join(package_dir, 'youtube_package.json'), 'w', encoding='utf-8') as file:
        json.dump(package, file, ensure_ascii=False, indent=2)

    if state.full_recap_export_dir and os.path.isdir(state.full_recap_export_dir):
        from pipeline.full_recap_renderer import add_youtube_package_to_export
        thumb_root = os.path.join(package_dir, 'thumbnails')
        thumbnails = [
            {
                **item,
                'path': os.path.join(thumb_root, item.get('filename', '')),
            }
            for item in state.full_recap_thumbnails
        ]
        add_youtube_package_to_export(
            state.full_recap_export_dir,
            titles=state.full_recap_titles,
            description=state.full_recap_description,
            pinned_comment=state.full_recap_pinned_comment,
            selected_title=state.full_recap_selected_title,
            thumbnails=thumbnails,
        )
    state.save()
    return jsonify({'status': 'selected', 'title': state.full_recap_selected_title})


@app.route('/api/full-recap/<project_name>/references/<kind>/<filename>', methods=['GET'])
def serve_full_recap_reference(project_name, kind, filename):
    from pipeline.full_recap_media import ALLOWED_IMAGE_EXTENSIONS
    if kind not in ('thumbnails', 'titles'):
        return jsonify({'error': 'Unknown reference kind'}), 404
    safe_name = os.path.basename(filename)
    if safe_name != filename or os.path.splitext(safe_name)[1].lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({'error': 'Invalid filename'}), 400
    state = PipelineState.load(project_name)
    folder = os.path.join(state.full_recap_workspace_dir or state.project_dir, 'full_recap', 'references', kind)
    if not os.path.isfile(os.path.join(folder, safe_name)):
        return jsonify({'error': 'Reference not found'}), 404
    return send_from_directory(folder, safe_name)


@app.route('/api/full-recap/<project_name>/thumbnails/<filename>', methods=['GET'])
def serve_full_recap_thumbnail(project_name, filename):
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        return jsonify({'error': 'Invalid filename'}), 400
    state = PipelineState.load(project_name)
    folder = os.path.join(state.full_recap_workspace_dir or state.project_dir, 'full_recap', 'thumbnails')
    if not os.path.isfile(os.path.join(folder, safe_name)):
        return jsonify({'error': 'Thumbnail not found'}), 404
    return send_from_directory(folder, safe_name)


@app.route('/api/full-recap/<project_name>/video', methods=['GET'])
def serve_full_recap_video(project_name):
    """Stream the rendered Full Recap MP4."""
    state = PipelineState.load(project_name)
    path = state.full_recap_video_path
    if not path or not os.path.isfile(path):
        return jsonify({'error': 'Full Recap video has not been rendered yet'}), 404
    return send_file(path, mimetype='video/mp4', as_attachment=False)


@app.route('/api/full-recap/<project_name>/export', methods=['GET'])
def download_full_recap_export(project_name):
    """Download the complete silent-video project folder as a ZIP archive."""
    import zipfile
    state = PipelineState.load(project_name)
    export_dir = state.full_recap_export_dir
    if not export_dir or not os.path.isdir(export_dir):
        return jsonify({'error': 'Сначала создайте немое видео и папку экспорта'}), 404

    archive_path = os.path.join(os.path.dirname(export_dir), 'full_recap_export.zip')
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        for root, _dirs, files in os.walk(export_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                archive.write(file_path, os.path.relpath(file_path, export_dir))

    download_name = f"{state.manhwa_name or project_name}_full_recap_export.zip"
    return send_file(archive_path, as_attachment=True, download_name=download_name)


@app.route('/api/full-recap/<project_name>/script/download', methods=['GET'])
def download_full_recap_script(project_name):
    """Download the complete Russian script as a standalone UTF-8 text file."""
    state = PipelineState.load(project_name)
    workspace = state.full_recap_workspace_dir or state.project_dir
    script_path = os.path.join(workspace, 'full_recap', 'script.txt')
    if not os.path.isfile(script_path):
        return jsonify({'error': 'Сначала создайте и сохраните сценарий'}), 404
    filename = f"{state.manhwa_name or project_name}_script.txt"
    return send_file(script_path, as_attachment=True, download_name=filename)


@app.route('/api/full-recap/<project_name>/script', methods=['PUT'])
def update_full_recap_script(project_name):
    """Save an edited recap script and recalculate its silent-video duration."""
    from pipeline.recap_script_writer import count_words, target_video_duration_seconds
    data = request.get_json(silent=True) or {}
    full_text = str(data.get('full_text') or '').strip()
    if not full_text:
        return jsonify({'error': 'Сценарий не может быть пустым'}), 400

    state = PipelineState.load(project_name)
    state.full_recap_script = full_text
    state.full_recap_word_count = count_words(full_text)
    state.full_recap_duration_seconds = target_video_duration_seconds(state.full_recap_word_count)
    state.full_recap_video_path = None
    state.full_recap_export_dir = None
    state.full_recap_status = 'script_edited'
    state.error = None

    workspace = state.full_recap_workspace_dir or state.project_dir
    script_dir = os.path.join(workspace, 'full_recap')
    os.makedirs(script_dir, exist_ok=True)
    with open(os.path.join(script_dir, 'script.txt'), 'w', encoding='utf-8') as file:
        file.write(full_text + '\n')
    state.save()
    return jsonify({
        'status': 'saved',
        'characters': len(full_text),
        'word_count': state.full_recap_word_count,
        'duration_seconds': state.full_recap_duration_seconds,
    })




@app.route('/api/projects/<name>/state', methods=['GET'])
def get_project_state(name):
    """Lightweight state read — just settings + panel metadata (no heavy image data)."""
    state = PipelineState.load(name)
    # Return a condensed panels list with only the fields the UI needs
    panels_slim = [
        {'panel_id': p.get('panel_id'), 'scene_id': p.get('scene_id')}
        for p in state.panels
    ]
    return jsonify({
        'stage': state.stage,
        'settings': state.settings,
        'panels': panels_slim,
        'video_path': state.video_path,
    })

# ─── Pipeline Execution ─────────────────────────────────────────
def _run_with_settings(step_fn, project_name, data):
    """Load state, patch settings from request data, then run step_fn."""
    state = PipelineState.load(project_name)
    settings_patch = data.get('settings', {})
    if settings_patch:
        state.settings.update(settings_patch)
        state.save()
    # Also accept top-level convenience keys
    for key in ('ollama_model', 'pipeline_mode', 'full_recap_text_model',
                'full_recap_style', 'full_recap_story_context', 'full_recap_target_words'):
        if key in data:
            state.settings[key] = data[key]
    return step_fn(state)


def _load_with_settings(project_name, source_folder, settings):
    """Load images and persist any settings sent alongside (incl. ⚡ Speed Mode)."""
    state = orchestrator.step_load_images(project_name, source_folder)
    if settings:
        state.settings.update(settings)
        state.save()
    return state


@app.route('/api/run/step/<step_name>', methods=['POST'])
def run_step(step_name):
    global pipeline_thread
    # ✅ GUARD: never start any step while another one is running — overlapping
    # threads corrupt per-chapter state (this caused the batch-mode bugs)
    if pipeline_thread and pipeline_thread.is_alive():
        return jsonify({
            'error': f'A pipeline step is already running. Wait for it to finish before starting {step_name}.',
            'status': 'busy'
        }), 409
    data = request.json
    project_name = data.get('project_name', '')
    step_map = {
        'load': lambda: _load_with_settings(project_name, data.get('source_folder', ''), data.get('settings', {})),
        # The original AniFlow image/OCR stages are invoked internally by one preparation command.
        'full_recap_prepare': lambda: orchestrator.step_full_recap_prepare(PipelineState.load(project_name)),
        'full_recap_script': lambda: _run_with_settings(orchestrator.step_full_recap_script, project_name, data),
        'full_recap_video': lambda: _run_with_settings(orchestrator.step_full_recap_video, project_name, data),
        'full_recap_package': lambda: _run_with_settings(orchestrator.step_full_recap_package, project_name, data),
    }
    if step_name not in step_map:
        return jsonify({'error': f'Unknown step: {step_name}'}), 400
    def run():
        orchestrator._should_cancel = False
        socketio.emit('step_started', {'step': step_name, 'project': project_name})
        state = step_map[step_name]()
        socketio.emit('step_complete', {'step': step_name, 'project': project_name,
            'stage': state.stage, 'error': state.error,
            'panels_count': len(state.panels), 'video_path': state.video_path})
    pipeline_thread = threading.Thread(target=run, daemon=True)
    pipeline_thread.start()
    return jsonify({'status': 'started', 'step': step_name})

@app.route('/api/debug', methods=['GET'])
def debug_info():
    return jsonify({
        'should_cancel': getattr(orchestrator, '_should_cancel', False),
        'thread_alive': pipeline_thread.is_alive() if pipeline_thread else False
    })

@app.route('/api/cancel', methods=['POST'])
def cancel_pipeline():
    orchestrator.cancel()
    return jsonify({'status': 'cancelling'})

# ─── AI Narration Backends ───────────────────────────────────────
@app.route('/api/gemini/validate-keys', methods=['POST'])
def gemini_validate_keys():
    """Validate each Gemini API key (multi-key support for cloud narration)."""
    data = request.json or {}
    keys = data.get('keys') or []
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.replace(',', '\n').split('\n')]
    from pipeline.gemini_narrator import validate_keys
    return jsonify({'results': validate_keys(keys)})


@app.route('/api/ai-backends', methods=['GET'])
def get_ai_backends():
    """Return available AI backends and their status."""
    backends = {
        'ollama': {'available': False, 'models': []},
        'gemini': {'available': True, 'models': ['gemini-2.5-flash', 'gemini-2.5-pro']},
        'claude': {'available': True, 'models': ['claude-sonnet-4-20250514', 'claude-opus-4-20250514']},
    }
    try:
        ollama_info = orchestrator.narrator.check_ollama()
        backends['ollama']['available'] = ollama_info.get('available', False)
        backends['ollama']['models'] = ollama_info.get('models', [])
    except Exception:
        pass
    return jsonify(backends)

# ─── Panel Management ────────────────────────────────────────────
@app.route('/api/projects/<project_name>/boxes', methods=['POST'])
def save_stitched_boxes(project_name):
    state = PipelineState.load(project_name)
    boxes = request.json.get('boxes', [])
    state.stitched_boxes = boxes
    state.stitched_boxes_1 = boxes  # Also update boxes_1 for two-stage compat
    state.save()
    return jsonify({'status': 'saved'})

@app.route('/api/projects/<project_name>/boxes2', methods=['POST'])
def save_stitched_boxes_2(project_name):
    state = PipelineState.load(project_name)
    boxes = request.json.get('boxes', [])
    state.stitched_boxes_2 = boxes
    state.save()
    return jsonify({'status': 'saved'})

@app.route('/api/panels/<project_name>/<int:panel_id>/text', methods=['PUT'])
def update_panel_text(project_name, panel_id):
    """Update the EXTRACTED DIALOGUE text of a bubble panel (dialogue-mode
    review step). Keeps everything downstream in sync:
      - panels_with_text[i]['text']          (used by the plot recap context)
      - art panels' inherited 'text'         (narration context)
      - output/extracted_txt/... .txt cache  ([PANEL N] blocks)
    """
    state = PipelineState.load(project_name)
    new_text = (request.json.get('text') or '').strip()

    target = next((p for p in state.panels_with_text if p.get('panel_id') == panel_id), None)
    if not target:
        # Fall back: maybe the id refers to an art panel whose parent we edit
        art = next((p for p in state.panels if p.get('panel_id') == panel_id), None)
        parent_id = art.get('parent_panel_id') if art else None
        target = next((p for p in state.panels_with_text if p.get('panel_id') == parent_id), None)
    if not target:
        return jsonify({'error': f'Panel {panel_id} not found'}), 404

    target['text'] = new_text
    target['dialogue'] = new_text

    # Keep mapped art panels' inherited text in sync
    for p in state.panels:
        if p.get('parent_panel_id') == target['panel_id']:
            p['text'] = new_text

    # Rewrite the [PANEL N] blocks in the extracted-txt cache so narration
    # and any cached re-runs see the corrected dialogue
    try:
        txt_path = os.path.join(config.EXTRACTED_TXT_DIR, state.manhwa_name,
                                f"Chapter_{state.current_chapter:05d}.txt")
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            import re as _re
            blocks = _re.split(r'(\[PANEL \d+\])', raw)
            out, replaced = [], False
            for chunk in blocks:
                if chunk.startswith('[PANEL') and chunk.rstrip(']').lstrip('[PANEL ').isdigit():
                    pid = int(chunk.rstrip(']').lstrip('[PANEL '))
                    out.append(chunk)
                    replaced = (pid == target['panel_id'])
                elif replaced:
                    out.append('\n' + (new_text or '(no dialogue)') + '\n')
                    replaced = False
                else:
                    out.append(chunk)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(''.join(out))
    except Exception as e:
        print(f"[TextEdit] Extracted-txt sync failed: {e}")

    state.save()
    return jsonify({'status': 'updated', 'panel_id': panel_id, 'text': new_text})


@app.route('/api/panels/<project_name>/<int:panel_id>', methods=['DELETE'])
def delete_panel(project_name, panel_id):
    """Delete a panel from the project — removes from state and deletes image file."""
    state = PipelineState.load(project_name)

    # Find and remove from panels list (check both panels and panels_with_text)
    panel = None
    for p in state.panels:
        if p.get('panel_id') == panel_id:
            panel = p
            break
    
    # Also check panels_with_text if not found in panels
    if not panel and state.panels_with_text:
        for p in state.panels_with_text:
            if p.get('panel_id') == panel_id:
                panel = p
                break

    if not panel:
        return jsonify({'error': f'Panel {panel_id} not found in panels or panels_with_text'}), 404

    # Delete image files from disk
    for key in ['path', 'clean_path', 'padded_path']:
        fpath = panel.get(key)
        if fpath and os.path.exists(fpath):
            try:
                os.remove(fpath)
                print(f"[DeletePanel] Deleted {fpath}")
            except Exception as e:
                print(f"[DeletePanel] Could not remove {fpath}: {e}")

    # Remove from panels list
    deleted_art_id = panel_id if any(p.get('panel_id') == panel_id for p in state.panels) else None
    state.panels = [p for p in state.panels if p.get('panel_id') != panel_id]

    # Also remove from panels_with_text if present
    deleted_pwt_id = None
    if state.panels_with_text:
        deleted_pwt_id = panel_id if any(p.get('panel_id') == panel_id for p in state.panels_with_text) else None
        state.panels_with_text = [p for p in state.panels_with_text if p.get('panel_id') != panel_id]

    # Re-number remaining panels sequentially
    old_art_ids = {}   # new_id -> old_id
    for i, p in enumerate(state.panels):
        old_art_ids[i + 1] = p['panel_id']
        p['panel_id'] = i + 1
    if state.panels_with_text:
        pwt_old_to_new = {}  # old_id -> new_id
        for i, p in enumerate(state.panels_with_text):
            pwt_old_to_new[p['panel_id']] = i + 1
            p['panel_id'] = i + 1
        # Remap parent_panel_id references onto the new bubble-panel ids
        for p in state.panels:
            old_parent = p.get('parent_panel_id')
            if old_parent is not None:
                p['parent_panel_id'] = pwt_old_to_new.get(old_parent, old_parent)

    # Keep panels_mapping keys in sync with the re-numbered art panels
    if state.panels_mapping is not None and deleted_art_id is not None:
        new_mapping = {}
        for p in state.panels:
            old_id = old_art_ids.get(p['panel_id'], p['panel_id'])
            entry = state.panels_mapping.get(str(old_id))
            if entry:
                new_mapping[str(p['panel_id'])] = entry
        state.panels_mapping = new_mapping

    state.save()
    print(f"[DeletePanel] Panel {panel_id} deleted. Remaining: {len(state.panels)} panels, {len(state.panels_with_text or [])} panels_with_text")
    return jsonify({'status': 'deleted', 'remaining': len(state.panels) + len(state.panels_with_text or [])})

@app.route('/api/panels/<project_name>/<int:panel_id>/crop', methods=['POST'])
def crop_panel(project_name, panel_id):
    """Crop a panel image to the specified region. Expects JSON { x, y, w, h } in pixels."""
    from PIL import Image as PILImage
    state = PipelineState.load(project_name)

    # Check both panels and panels_with_text
    panel = next((p for p in state.panels if p.get('panel_id') == panel_id), None)
    if not panel and state.panels_with_text:
        panel = next((p for p in state.panels_with_text if p.get('panel_id') == panel_id), None)
    
    if not panel:
        return jsonify({'error': f'Panel {panel_id} not found. Total panels: {len(state.panels)}, panels_with_text: {len(state.panels_with_text or [])}'}), 404

    data = request.json
    x = int(data.get('x', 0))
    y = int(data.get('y', 0))
    w = int(data.get('w', 0))
    h = int(data.get('h', 0))

    if w <= 0 or h <= 0:
        return jsonify({'error': 'Invalid crop dimensions'}), 400

    # Crop the main panel image
    img_path = panel.get('path')
    if not img_path or not os.path.exists(img_path):
        return jsonify({'error': f'Panel image not found at {img_path}'}), 404

    try:
        img = PILImage.open(img_path)
        orig_w, orig_h = img.size
        # Clamp crop region to image bounds
        x2 = min(x + w, orig_w)
        y2 = min(y + h, orig_h)
        cropped = img.crop((max(0, x), max(0, y), x2, y2))
        cropped.save(img_path)
        new_w, new_h = cropped.size
        img.close()
        cropped.close()

        print(f"[CropPanel] Panel {panel_id} cropped from ({orig_w}x{orig_h}) to ({new_w}x{new_h})")

        # Also crop clean_path and padded_path if they exist
        for key in ['clean_path', 'padded_path']:
            fpath = panel.get(key)
            if fpath and os.path.exists(fpath):
                try:
                    alt_img = PILImage.open(fpath)
                    alt_cropped = alt_img.crop((max(0, x), max(0, y), x2, y2))
                    alt_cropped.save(fpath)
                    alt_img.close()
                    alt_cropped.close()
                except Exception as e:
                    print(f"[CropPanel] Could not crop {key}: {e}")

        state.save()
        return jsonify({'status': 'cropped', 'new_width': new_w, 'new_height': new_h})

    except Exception as e:
        return jsonify({'error': f'Crop failed: {str(e)}'}), 500


# ─── Script Rewriter ─────────────────────────────────────────────
@app.route('/api/preview-detection/<project_name>/<path:page_filename>', methods=['GET'])
def preview_detection(project_name, page_filename):
    state = PipelineState.load(project_name)
    raw_dir = os.path.join(state.project_dir, "raw_pages")
    image_path = os.path.join(raw_dir, page_filename)
    if not os.path.exists(image_path):
        return jsonify({'error': 'Image not found'}), 404
        
    try:
        extractor = get_global_extractor()
        jpeg_bytes = extractor.preview_page(image_path)
        return Response(jpeg_bytes, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Cast System ─────────────────────────────────────────────────
@app.route('/api/casts', methods=['GET'])
def get_casts():
    return jsonify(list_casts())

@app.route('/api/casts/export/<project_name>', methods=['POST'])
def export_cast(project_name):
    try:
        filepath = orchestrator.export_cast(project_name)
        return jsonify({'status': 'exported', 'path': filepath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/casts/import', methods=['POST'])
def import_cast():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    filepath = os.path.join(config.CAST_DIR, f.filename)
    f.save(filepath)
    try:
        cast = Cast.load(filepath)
        return jsonify({'status': 'imported', 'cast': cast.to_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/casts/<name>', methods=['GET'])
def get_cast(name):
    filepath = os.path.join(config.CAST_DIR, f"{name}.cst")
    if not os.path.exists(filepath):
        return jsonify({'error': 'Cast not found'}), 404
    cast = Cast.load(filepath)
    return jsonify(cast.to_dict())

@app.route('/api/casts/<name>', methods=['PUT'])
def update_cast(name):
    filepath = os.path.join(config.CAST_DIR, f"{name}.cst")
    data = request.json
    cast = Cast.from_dict(data)
    cast.save(filepath)
    return jsonify({'status': 'updated'})

@app.route('/api/casts/<name>', methods=['DELETE'])
def delete_cast(name):
    filepath = os.path.join(config.CAST_DIR, f"{name}.cst")
    if os.path.exists(filepath):
        os.remove(filepath)
    return jsonify({'status': 'deleted'})

@app.route('/api/casts/download/<name>')
def download_cast(name):
    filepath = os.path.join(config.CAST_DIR, f"{name}.cst")
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=f"{name}.cst")
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/casts/scan-manga', methods=['GET'])
def scan_manga_for_cast():
    """Scan downloaded manga directory and return available manga with chapter info."""
    root = get_download_root()
    if not os.path.exists(root):
        return jsonify([])
    manga_list = []
    for name in sorted(os.listdir(root)):
        manga_dir = os.path.join(root, name)
        if not os.path.isdir(manga_dir):
            continue
        chapters = []
        for ch_name in sorted(os.listdir(manga_dir)):
            ch_dir = os.path.join(manga_dir, ch_name)
            if not os.path.isdir(ch_dir) or not ch_name.startswith('Chapter'):
                continue
            images = [f for f in os.listdir(ch_dir) if f.lower().endswith(('.jpg','.jpeg','.png','.webp','.gif'))]
            chapters.append({'name': ch_name, 'image_count': len(images)})
        if chapters:
            # Load cover from metadata if available
            cover = None
            meta_path = os.path.join(manga_dir, 'manga_info.json')
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                        cover = meta.get('cover_url')
                except Exception:
                    pass
            manga_list.append({
                'name': name,
                'path': manga_dir,
                'chapters': chapters,
                'total_chapters': len(chapters),
                'total_images': sum(c['image_count'] for c in chapters),
                'cover_url': cover,
            })
    return jsonify(manga_list)

@app.route('/api/casts/build-from-manga', methods=['POST'])
def build_cast_from_manga():
    """Build character cast by scanning images from selected manga chapters.
    Sends images to Ollama vision model to detect characters."""
    global pipeline_thread
    data = request.json
    manga_path = data.get('manga_path', '')
    chapter_from = data.get('chapter_from', 1)
    chapter_to = data.get('chapter_to', 1)
    cast_name = data.get('cast_name', 'auto-cast')
    if not manga_path or not os.path.isdir(manga_path):
        return jsonify({'error': 'Invalid manga path'}), 400
    def run():
        socketio.emit('step_started', {'step': 'build_cast', 'project': 'cast'})
        try:
            # Collect all images from the selected chapter range
            all_images = []
            for ch_name in sorted(os.listdir(manga_path)):
                if not ch_name.startswith('Chapter') or not os.path.isdir(os.path.join(manga_path, ch_name)):
                    continue
                # Extract chapter number
                import re
                num_match = re.search(r'(\d+)', ch_name)
                if not num_match:
                    continue
                ch_num = int(num_match.group(1))
                if ch_num < chapter_from or ch_num > chapter_to:
                    continue
                ch_dir = os.path.join(manga_path, ch_name)
                for img_name in sorted(os.listdir(ch_dir)):
                    if img_name.lower().endswith(('.jpg','.jpeg','.png','.webp','.gif')):
                        all_images.append(os.path.join(ch_dir, img_name))

            if not all_images:
                socketio.emit('step_complete', {'step': 'build_cast', 'project': 'cast',
                    'stage': 'error', 'error': 'No images found in selected chapters'})
                return

            socketio.emit('progress', {'stage': 'build_cast', 'current': 0, 'total': len(all_images),
                'message': f'Scanning {len(all_images)} images for characters...', 'percent': 0})

            # Use Ollama to detect characters from a sample of images
            detected_chars = {}
            sample_size = min(len(all_images), 30)  # Analyse up to 30 images
            import random
            sample = sorted(random.sample(all_images, sample_size)) if len(all_images) > sample_size else all_images

            for idx, img_path in enumerate(sample):
                socketio.emit('progress', {'stage': 'build_cast', 'current': idx + 1, 'total': len(sample),
                    'message': f'Analyzing image {idx+1}/{len(sample)}...', 'percent': int(((idx+1)/len(sample))*100)})
                try:
                    chars = orchestrator.narrator.detect_characters(img_path)
                    for ch in chars:
                        name = ch.get('name', '').strip()
                        if name and name.lower() not in ('unknown', 'narrator', 'n/a', 'none', ''):
                            if name not in detected_chars:
                                detected_chars[name] = {'count': 0, 'description': ch.get('description', '')}
                            detected_chars[name]['count'] += 1
                except Exception as e:
                    print(f"[Cast] Error analyzing {img_path}: {e}")

            # Build the cast from detected characters
            cast = Cast(name=cast_name)
            voices = ['en-US-ChristopherNeural', 'en-US-GuyNeural', 'en-US-DavisNeural',
                       'en-US-JennyNeural', 'en-GB-RyanNeural', 'en-US-AriaNeural',
                       'en-US-JasonNeural', 'en-US-SaraNeural']
            for i, (char_name, info) in enumerate(sorted(detected_chars.items(), key=lambda x: -x[1]['count'])):
                voice = voices[i % len(voices)]
                cast.add_character(char_name, voice=voice)

            filepath = cast.save()
            socketio.emit('step_complete', {'step': 'build_cast', 'project': 'cast',
                'stage': 'done', 'error': None,
                'result': {
                    'cast_name': cast_name,
                    'characters': len(detected_chars),
                    'images_scanned': len(sample),
                    'detected': {k: v['count'] for k, v in detected_chars.items()},
                    'path': filepath,
                }})
        except Exception as e:
            socketio.emit('step_complete', {'step': 'build_cast', 'project': 'cast',
                'stage': 'error', 'error': str(e)})
    pipeline_thread = threading.Thread(target=run, daemon=True)
    pipeline_thread.start()
    return jsonify({'status': 'started'})

# ─── Character Builder ───────────────────────────────────────────
@app.route('/api/charbuilder/scan', methods=['POST'])
def charbuilder_scan():
    """Scan manga chapters and extract face crops."""
    global pipeline_thread
    data = request.json
    manga_path = data.get('manga_path', '')
    ch_from = data.get('chapter_from', 1)
    ch_to = data.get('chapter_to', 3)
    if not manga_path or not os.path.isdir(manga_path):
        return jsonify({'error': 'Invalid manga path'}), 400
    def run():
        socketio.emit('progress', {'stage': 'char_scan', 'current': 0, 'total': 1, 'message': 'Scanning faces...', 'percent': 0})
        try:
            sid, faces = charbuilder.scan_faces(manga_path, ch_from, ch_to)
            socketio.emit('step_complete', {'step': 'char_scan', 'error': None,
                'result': {'session_id': sid, 'faces': faces, 'total': len(faces)}})
        except Exception as e:
            socketio.emit('step_complete', {'step': 'char_scan', 'error': str(e)})
    pipeline_thread = threading.Thread(target=run, daemon=True)
    pipeline_thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/charbuilder/face/<session_id>/<filename>')
def serve_scan_face(session_id, filename):
    p = charbuilder.get_face_image_path(session_id, filename)
    if os.path.exists(p):
        return send_file(p)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/charbuilder/charface/<cast_name>/<filename>')
def serve_char_face(cast_name, filename):
    p = charbuilder.get_char_face_path(cast_name, filename)
    if os.path.exists(p):
        return send_file(p)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/charbuilder/save', methods=['POST'])
def charbuilder_save():
    data = request.json
    char = charbuilder.save_character(
        data['cast_name'], data['name'], data['gender'],
        data['face_indices'], data['session_id'])
    return jsonify({'status': 'saved', 'character': char})

@app.route('/api/charbuilder/characters/<cast_name>')
def charbuilder_list(cast_name):
    return jsonify(charbuilder.load_characters(cast_name))

@app.route('/api/charbuilder/character/<cast_name>/<char_id>', methods=['DELETE'])
def charbuilder_delete(cast_name, char_id):
    charbuilder.delete_character(cast_name, char_id)
    return jsonify({'status': 'deleted'})


@app.route('/api/charbuilder/export/<cast_name>')
def charbuilder_export(cast_name):
    """Download a cast as a .cast.zip bundle (characters.json + face images)."""
    import zipfile
    # Safety: reject path traversal
    if (not cast_name or '/' in cast_name or '\\' in cast_name or '..' in cast_name):
        return jsonify({'error': 'Invalid cast name'}), 400
    cast_dir = os.path.join(charbuilder.CAST_DATA_DIR, cast_name)
    if not os.path.isdir(cast_dir):
        return jsonify({'error': 'Cast not found'}), 404
    zip_path = os.path.join(config.TEMP_DIR, f"{cast_name}.cast.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(cast_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                zf.write(fpath, os.path.relpath(fpath, cast_dir))
    return send_file(zip_path, as_attachment=True, download_name=f"{cast_name}.cast.zip")


@app.route('/api/charbuilder/import/<cast_name>', methods=['POST'])
def charbuilder_import(cast_name):
    """Import a .cast.zip bundle produced by the export endpoint (merge into cast)."""
    import zipfile
    if (not cast_name or '/' in cast_name or '\\' in cast_name or '..' in cast_name):
        return jsonify({'error': 'Invalid cast name'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    cast_dir = os.path.join(charbuilder.CAST_DATA_DIR, cast_name)
    os.makedirs(cast_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(f) as zf:
            for member in zf.namelist():
                # Guard against zip-slip path traversal
                clean = os.path.normpath(member).lstrip('/\\')
                if clean.startswith('..') or ':' in clean:
                    continue
                target = os.path.join(cast_dir, clean)
                if member.endswith('/'):
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
        chars = charbuilder.load_characters(cast_name)
        return jsonify({'status': 'imported', 'characters': len(chars)})
    except zipfile.BadZipFile:
        return jsonify({'error': 'Not a valid cast archive (.cast.zip)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/charbuilder/character/<cast_name>/<char_id>', methods=['PUT'])
def charbuilder_update(cast_name, char_id):
    data = request.json
    char = charbuilder.update_character(cast_name, char_id, data.get('name'), data.get('gender'))
    return jsonify({'status': 'updated', 'character': char})

@app.route('/api/charbuilder/find-similar', methods=['POST'])
def charbuilder_find_similar():
    """Find faces similar to a reference face."""
    data = request.json
    session_id = data.get('session_id')
    ref_index = data.get('reference_index')
    all_faces = data.get('faces', [])
    threshold = data.get('threshold', 0.55)
    similar = charbuilder.find_similar_faces(session_id, ref_index, all_faces, threshold)
    return jsonify({'similar_indices': similar, 'count': len(similar)})

@app.route('/api/charbuilder/mal-search')
def charbuilder_mal_search():
    """Search MyAnimeList manga by name. Returns the first matches."""
    from pipeline.mal_character_importer import search_mal_manga
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'error': 'q is required'}), 400
    return jsonify({'results': search_mal_manga(q, limit=5)})


@app.route('/api/charbuilder/import-from-mal', methods=['POST'])
def charbuilder_import_from_mal():
    """Import characters from MyAnimeList into a cast."""
    try:
        from pipeline.mal_character_importer import scrape_characters_from_mal, import_characters_to_cast

        data = request.json
        mal_url = data.get('mal_url', '').strip()
        cast_name = data.get('cast_name', '').strip()
        max_characters = data.get('max_characters', 20)
        download_images = data.get('download_images', True)

        if not mal_url or not cast_name:
            return jsonify({'error': 'mal_url and cast_name are required'}), 400

        characters = scrape_characters_from_mal(mal_url, max_characters=max_characters)

        if not characters:
            return jsonify({'error': 'No characters found at that URL — check it opens in a browser'}), 404

        result = import_characters_to_cast(characters, cast_name, download_images=download_images)

        return jsonify({
            'status': 'success',
            'imported': result['imported'],
            'total': result['total'],
            'characters': [{'name': c['name'], 'role': c['role'],
                            'image': bool(c['reference_images'])}
                           for c in result['characters']],
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/charbuilder/add-bulk', methods=['POST'])
def charbuilder_add_bulk():
    """Manually add character names (comma/newline separated) to a cast."""
    try:
        from pipeline.mal_character_importer import add_bulk_characters
        data = request.json or {}
        cast_name = data.get('cast_name', '').strip()
        raw = data.get('names', '')
        if not cast_name:
            return jsonify({'error': 'cast_name is required'}), 400
        names = [n for n in re.split(r'[,\n]+', raw) if n.strip()]
        if not names:
            return jsonify({'error': 'No names provided'}), 400
        result = add_bulk_characters(names, cast_name)
        return jsonify({'status': 'success', 'added': result['added'],
                        'total': result['total']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── CapCut Director ─────────────────────────────────────────────
@app.route('/api/export/panels/<project_name>', methods=['GET'])
def export_panels_zip(project_name):
    import zipfile
    state = PipelineState.load(project_name)
    zip_path = os.path.join(config.TEMP_DIR, f"{project_name}_panels.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for p in state.panels:
            if os.path.exists(p['path']):
                zf.write(p['path'], os.path.basename(p['path']))
    return send_file(zip_path, as_attachment=True, download_name=f"{project_name}_panels.zip")

# ─── File Serving ────────────────────────────────────────────────
@app.route('/api/panel-image/<project_name>/<filename>')
def serve_panel_image(project_name, filename):
    state = PipelineState.load(project_name)
    # Search all panel lists: panels, panels_with_text
    all_panels = (state.panels or []) + (state.panels_with_text or [])
    for p in all_panels:
        if os.path.basename(p.get('path', '')) == filename:
            if os.path.exists(p['path']):
                return send_file(p['path'])
    # Fallback: check crop_dir and project_dir directly
    for search_dir in [state.crop_dir, state.project_dir]:
        direct_path = os.path.join(search_dir, filename)
        if os.path.exists(direct_path):
            return send_file(direct_path)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/clean-panel-image/<project_name>/<filename>')
def serve_clean_panel_image(project_name, filename):
    """Serve a panel image with text boxes removed."""
    state = PipelineState.load(project_name)
    # Search all panel lists: panels, panels_with_text
    all_panels = (state.panels or []) + (state.panels_with_text or [])
    for p in all_panels:
        if os.path.basename(p.get('path', '')) == filename:
            clean_path = p.get('clean_path')
            if clean_path and os.path.exists(clean_path):
                return send_file(clean_path)
            # Fallback to original
            if os.path.exists(p['path']):
                return send_file(p['path'])
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/page-image/<project_name>/<filename>')
def serve_page_image(project_name, filename):
    return send_from_directory(os.path.join(config.PROJECTS_DIR, project_name, "raw_pages"), filename)

@app.route('/api/raw-page-image/<project_name>/<filename>')
def serve_raw_page_image(project_name, filename):
    """Alias for page-image — serves raw pages for the stitch preview thumbnail strip."""
    return send_from_directory(os.path.join(config.PROJECTS_DIR, project_name, "raw_pages"), filename)

@app.route('/api/panel-text/<project_name>')
def serve_panel_texts(project_name):
    """Serve the extracted panel texts file."""
    txt_path = os.path.join(config.PROJECTS_DIR, project_name, "panel_texts.txt")
    if os.path.exists(txt_path):
        return send_file(txt_path, mimetype='text/plain')
    return jsonify({'error': 'Panel texts not found'}), 404

@app.route('/api/stitched-image/<project_name>', methods=['GET', 'HEAD'])
def get_stitched_image(project_name):
    state = PipelineState.load(project_name)
    print(f"[get_stitched_image] Loaded chapter {state.current_chapter}, is_batch={state.is_batch}")
    print(f"[get_stitched_image] stitched_parts: {state.stitched_parts[:2] if state.stitched_parts else 'None'}")
    
    if hasattr(state, 'stitched_path') and state.stitched_path and os.path.exists(state.stitched_path):
        return jsonify({'parts': [f"/api/raw-image?path={urllib.parse.quote(state.stitched_path)}"]})
    if state.stitched_parts:
        import urllib.parse
        # ✅ PERFORMANCE: version the URLs by content mtime — the browser caches
        # chapter images across switches, and re-stitching (new mtime) busts it.
        try:
            version = int(max(os.path.getmtime(p) for p in state.stitched_parts
                              if os.path.exists(p)) * 1000)
        except Exception:
            version = 0
        parts_urls = [f"/api/raw-image?path={urllib.parse.quote(p)}&v={version}"
                      for p in state.stitched_parts]
        print(f"[get_stitched_image] Returning {len(parts_urls)} parts for chapter {state.current_chapter}")
        return jsonify({'parts': parts_urls})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/stitched-image-2/<project_name>', methods=['GET', 'HEAD'])
def get_stitched_image_2(project_name):
    """Serve Stitched Image 2 parts (re-stitched panels-with-text)."""
    state = PipelineState.load(project_name)
    if state.stitched_parts_2:
        import urllib.parse
        parts_urls = [f"/api/raw-image?path={urllib.parse.quote(p)}" for p in state.stitched_parts_2]
        return jsonify({'parts': parts_urls})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/raw-image')
def serve_raw_image():
    import urllib.parse
    path = request.args.get('path')
    if path and os.path.exists(path):
        return send_file(path)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/stitched-detected/<project_name>', methods=['GET', 'HEAD'])
def get_stitched_detected_image(project_name):
    state = PipelineState.load(project_name)
    if hasattr(state, 'stitched_preview_path') and state.stitched_preview_path and os.path.exists(state.stitched_preview_path):
        return send_file(state.stitched_preview_path)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/ollama/models', methods=['GET'])
def get_ollama_models():
    return jsonify(orchestrator.narrator.check_ollama())

# ─── Asset Management ────────────────────────────────────────────
@app.route('/api/assets/<asset_type>', methods=['GET'])
def list_assets(asset_type):
    dir_map = {'bgm': config.BGM_DIR, 'watermarks': config.WATERMARK_DIR,
               'backgrounds': config.BACKGROUNDS_DIR, 'intros': config.INTROS_DIR, 'outros': config.OUTROS_DIR}
    asset_dir = dir_map.get(asset_type)
    if not asset_dir:
        return jsonify({'error': 'Invalid asset type'}), 400
    files = []
    for f in sorted(os.listdir(asset_dir)):
        fp = os.path.join(asset_dir, f)
        if os.path.isfile(fp):
            files.append({'name': f, 'path': fp, 'size': os.path.getsize(fp)})
    return jsonify(files)

@app.route('/api/assets/<asset_type>/upload', methods=['POST'])
def upload_asset(asset_type):
    dir_map = {'bgm': config.BGM_DIR, 'watermarks': config.WATERMARK_DIR,
               'backgrounds': config.BACKGROUNDS_DIR, 'intros': config.INTROS_DIR, 'outros': config.OUTROS_DIR}
    asset_dir = dir_map.get(asset_type)
    if not asset_dir:
        return jsonify({'error': 'Invalid asset type'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['file']
    filepath = os.path.join(asset_dir, f.filename)
    f.save(filepath)
    return jsonify({'status': 'uploaded', 'path': filepath, 'name': f.filename})

# ─── Manhwa Chapter Downloader ───────────────────────────────────
@app.route('/api/scraper/analyze', methods=['POST'])
def scraper_analyze():
    """Analyze a manhwa URL with a real timeout.

    NOTE: must NOT use `with ThreadPoolExecutor()` here — its __exit__ waits
    for the submitted thread to finish, so a hung site fetch would block the
    request forever even after the timeout fired (the 4-minute 'Analyzing'
    hang). A detached daemon thread lets the response return on time.
    """
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    result_holder = {}

    def _work():
        try:
            result_holder['result'] = analyze_url(url)
        except Exception as e:
            result_holder['error'] = str(e)

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    th.join(timeout=90)

    if th.is_alive():
        return jsonify({
            'error': 'The site took too long to respond (90s). It may be down or '
                     'blocking us - try again in a moment, or use a MangaDex URL instead.',
            'timeout': True
        }), 504
    if 'error' in result_holder:
        return jsonify({'error': result_holder['error']}), 500
    return jsonify(result_holder['result'])

@app.route('/api/scraper/download', methods=['POST'])
def scraper_download():
    global pipeline_thread
    # ✅ GUARD: don't stack downloads — same thread slot as pipeline steps
    if pipeline_thread and pipeline_thread.is_alive():
        return jsonify({'error': 'A task is already running. Wait for it to finish.', 'status': 'busy'}), 409
    data = request.json
    manga_url = data.get('url', '').strip()
    chapters = data.get('chapters', [])
    if not manga_url or not chapters:
        return jsonify({'error': 'URL and chapters are required'}), 400
    def run():
        socketio.emit('step_started', {'step': 'download_chapters', 'project': 'scraper'})
        def cb(current, total, msg):
            socketio.emit('progress', {'stage': 'download', 'current': current, 'total': total,
                                       'message': msg, 'percent': int((current / max(total, 1)) * 100)})
        try:
            result = download_chapters(manga_url, chapters, progress_callback=cb)
            socketio.emit('step_complete', {'step': 'download_chapters', 'project': 'scraper',
                'stage': 'done', 'error': None, 'result': result})
        except Exception as e:
            socketio.emit('step_complete', {'step': 'download_chapters', 'project': 'scraper',
                'stage': 'error', 'error': str(e)})
    pipeline_thread = threading.Thread(target=run, daemon=True)
    pipeline_thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/scraper/downloaded', methods=['GET'])
def scraper_list_downloaded():
    return jsonify(list_downloaded_manga())

@app.route('/api/scraper/download-root', methods=['GET'])
def scraper_download_root():
    root = get_download_root()
    os.makedirs(root, exist_ok=True)
    return jsonify({'path': root})

@app.route('/api/scraper/chapter-image/<path:filepath>')
def serve_scraped_image(filepath):
    """Serve downloaded chapter images for preview."""
    root = get_download_root()
    full = os.path.join(root, filepath)
    if os.path.exists(full):
        return send_file(full)
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/raw-json')
def serve_raw_json():
    """Serve a manga_info.json from the download root (path-validated)."""
    path = request.args.get('path', '')
    root = os.path.realpath(get_download_root())
    real = os.path.realpath(path) if path else ''
    if not real or not real.startswith(root + os.sep) or not os.path.isfile(real):
        return jsonify({'error': 'Invalid path'}), 400
    if not real.endswith('manga_info.json'):
        return jsonify({'error': 'Only manga_info.json allowed'}), 400
    try:
        with open(real, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── WebSocket Events ────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'ok'})

@socketio.on('disconnect')
def handle_disconnect():
    pass

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  🎬 AniFlow - Automated Manhwa Video Creation")
    print("  Open http://localhost:8080 in your browser")
    print("="*60 + "\n")
    socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True)
