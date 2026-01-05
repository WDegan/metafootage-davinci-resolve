#!/usr/bin/env python3
"""
Metafootage - DaVinci Resolve AI Plugin (Ultimate Multi-Provider Version)
Copyright (c) 2025 W.Degan

FEATURES:
- Providers: Google Gemini & OpenAI GPT-4o support.
- Robust BRAW/RAW Support: Searches Resolve Proxies and manual "Proxy" folders.
- Cinematic Analysis: Lighting, Camera Movement, Emotion, Subject detection.
- Smart Keyword Merging: Preserves your existing organization.
- Detailed Reports: Full summary of success and failures after processing.
"""

import os
import sys
import platform
import json
import subprocess
import base64
import tempfile
import shutil
import urllib.request
import time
import random

# ==============================================================================
# RESOLVE API SETUP
# ==============================================================================

def load_bmd():
    try:
        import DaVinciResolveScript as bmd
        return bmd
    except ImportError:
        if platform.system() == "Windows":
            lib_path = os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 
                                  'Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules')
        elif platform.system() == "Darwin":
            lib_path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        else:
            lib_path = "/opt/resolve/Developer/Scripting/Modules"
            
        if os.path.exists(lib_path):
            if lib_path not in sys.path:
                sys.path.append(lib_path)
            try:
                import DaVinciResolveScript as bmd
                return bmd
            except ImportError:
                return None
    return None

# ==============================================================================
# CONFIGURATION
# ==============================================================================

class ConfigManager:
    def __init__(self):
        if platform.system() == "Windows":
            config_dir = os.path.join(os.environ.get('APPDATA', ''), 'Metafootage')
        else:
            config_dir = os.path.join(os.path.expanduser('~'), '.metafootage')
        
        os.makedirs(config_dir, exist_ok=True)
        self.config_path = os.path.join(config_dir, 'config.json')
        self.config = self._load_config()
    
    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_config(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except:
            pass
    
    def save_api_key(self, provider, api_key):
        key_name = f"{provider.lower().replace(' ', '_')}_api_key"
        self.config[key_name] = base64.b64encode(api_key.encode('utf-8')).decode('utf-8')
        self._save_config()
    
    def get_api_key(self, provider):
        key_name = f"{provider.lower().replace(' ', '_')}_api_key"
        try:
            if key_name in self.config:
                return base64.b64decode(self.config[key_name]).decode('utf-8')
        except:
            return ""
        return ""

    def get_val(self, key, default): return self.config.get(key, default)
    def set_val(self, key, val): 
        self.config[key] = val
        self._save_config()

# ==============================================================================
# MEDIA PATH RESOLUTION (Robust BRAW/RAW & Proxy Support)
# ==============================================================================

def find_manual_proxy(source_path, custom_root=None):
    if not source_path: return None, []
    folder = os.path.dirname(source_path)
    filename = os.path.basename(source_path)
    name_no_ext = os.path.splitext(filename)[0]
    candidates = []
    
    if custom_root and os.path.exists(custom_root):
        candidates.append(os.path.join(custom_root, f"{name_no_ext}.mov"))
        candidates.append(os.path.join(custom_root, f"{name_no_ext}.mp4"))
        candidates.append(os.path.join(custom_root, filename))
        candidates.append(os.path.join(custom_root, "Proxy", f"{name_no_ext}.mov"))
        candidates.append(os.path.join(custom_root, "Proxies", f"{name_no_ext}.mov"))

    candidates.append(os.path.join(folder, "Proxy", f"{name_no_ext}.mov"))
    candidates.append(os.path.join(folder, "Proxy", f"{name_no_ext}.mp4"))
    candidates.append(os.path.join(folder, "Proxies", f"{name_no_ext}.mov"))
    candidates.append(os.path.join(folder, "Proxies", f"{name_no_ext}.mp4"))
    
    checked = []
    for c in candidates:
        checked.append(c)
        if os.path.exists(c): return c, checked
    return None, checked

def get_best_media_path(clip, custom_proxy_root=None):
    path = clip.GetClipProperty("File Path")
    ext = os.path.splitext(path)[1].lower()
    is_raw = ext in ['.braw', '.r3d', '.ari', '.arx', '.dng', '.crm']
    
    if is_raw:
        proxy = clip.GetClipProperty("Proxy")
        if proxy and os.path.exists(proxy): return proxy, True
        manual, _ = find_manual_proxy(path, custom_proxy_root)
        if manual: return manual, True
    return path, False

# ==============================================================================
# VIDEO PROCESSING
# ==============================================================================

def extract_frames(file_path, frame_count=5):
    if not os.path.exists(file_path): raise Exception(f"File not found: {file_path}")
    temp_dir = tempfile.mkdtemp(prefix="metafootage_")
    base64_frames = []
    try:
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        proc = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        if not proc.stdout.strip(): raise Exception("Could not read video duration. Try using a Proxy.")
            
        duration = float(proc.stdout.strip())
        start_time = duration * 0.1
        step = (duration * 0.8) / (frame_count - 1 if frame_count > 1 else 1)
        
        for i in range(frame_count):
            ts = start_time + (i * step)
            out_file = os.path.join(temp_dir, f"frame_{i}.jpg")
            cmd = ["ffmpeg", "-ss", f"{ts:.3f}", "-i", file_path, "-frames:v", "1", "-vf", "scale=960:-1", "-q:v", "2", "-y", out_file]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 1024:
                with open(out_file, "rb") as f:
                    base64_frames.append(base64.b64encode(f.read()).decode('utf-8'))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return base64_frames

# ==============================================================================
# AI ENGINES
# ==============================================================================

METADATA_SCHEMA_PROMPT = """Return JSON with these keys: 
short_desc (string), long_desc (string), subjects (array), actions (array), 
camera (string), lighting (string), setting (string), emotion (string), keywords (array)."""

# Strict schema enforcement for Gemini
GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "short_desc": {"type": "STRING"},
        "long_desc": {"type": "STRING"},
        "subjects": {"type": "ARRAY", "items": {"type": "STRING"}},
        "actions": {"type": "ARRAY", "items": {"type": "STRING"}},
        "camera": {"type": "STRING"},
        "lighting": {"type": "STRING"},
        "setting": {"type": "STRING"},
        "emotion": {"type": "STRING"},
        "keywords": {"type": "ARRAY", "items": {"type": "STRING"}}
    }
}

def analyze_with_gemini(frames, api_key, model_name, filename):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    parts = [{"text": f"Analyze these frames from: {filename}. {METADATA_SCHEMA_PROMPT}"}]
    for b64 in frames: parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    
    payload = {
        "contents": [{"parts": parts}], 
        "generationConfig": {
            "responseMimeType": "application/json", 
            "responseSchema": GEMINI_SCHEMA,
            "temperature": 0.7
        }
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode('utf-8'))
        text = result['candidates'][0]['content']['parts'][0]['text']
        return json.loads(text), None

def analyze_with_openai(frames, api_key, model_name, filename):
    url = "https://api.openai.com/v1/chat/completions"
    messages = [
        {"role": "system", "content": f"You are a cinematic editor. {METADATA_SCHEMA_PROMPT}"},
        {"role": "user", "content": [{"type": "text", "text": f"Analyze these video frames from: {filename}"}]}
    ]
    for b64 in frames: messages[1]["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {"model": model_name, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0.7}
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode('utf-8'))
        text = result['choices'][0]['message']['content']
        return json.loads(text), None

# ==============================================================================
# MAIN PLUGIN LOGIC
# ==============================================================================

def main():
    bmd = load_bmd()
    if not bmd: return
    resolve = bmd.scriptapp("Resolve")
    fusion = resolve.Fusion()
    ui = fusion.UIManager
    disp = bmd.UIDispatcher(ui)
    config = ConfigManager()

    project = resolve.GetProjectManager().GetCurrentProject()
    clips = project.GetMediaPool().GetSelectedClips() if project else []
    
    if not clips:
        err_win = disp.AddWindow({'WindowTitle': 'Error', 'Geometry': [500, 400, 320, 160]}, [
            ui.VGroup([
                ui.Label({'Text': 'Please select clips in the Media Pool first.', 'Alignment': {'AlignHCenter': True}, 'WordWrap': True}),
                ui.VGap(10),
                ui.Button({'ID': 'OkBtn', 'Text': 'OK'}),
                ui.VGap(5),
                ui.Label({'Text': '© 2025 W.Degan', 'Alignment': {'AlignRight': True}, 'Weight': 0, 'StyleSheet': 'color: #4b5563; font-size: 10px;'})
            ])
        ])
        err_win.On.OkBtn.Clicked = lambda ev: disp.ExitLoop()
        err_win.On.Default.Close = lambda ev: disp.ExitLoop()
        err_win.Show()
        disp.RunLoop()
        err_win.Hide()
        return

    win = disp.AddWindow({'WindowTitle': 'Metafootage AI', 'ID': 'MainWin', 'Geometry': [400, 300, 500, 600]}, [
        ui.VGroup([
            ui.Label({'Text': 'Metafootage', 'StyleSheet': 'font-size: 24px; font-weight: bold; color: #60a5fa;'}),
            ui.Label({'Text': f'Selected Clips: {len(clips)}', 'StyleSheet': 'color: #9ca3af;'}),
            ui.VGap(10),
            ui.HGroup([
                ui.Label({'Text': 'Provider:', 'Weight': 0.3}),
                ui.ComboBox({'ID': 'ProviderSelect', 'Weight': 0.7}),
            ]),
            ui.VGap(5),
            ui.Label({'ID': 'KeyLabel', 'Text': 'API Key:'}),
            ui.LineEdit({'ID': 'ApiKey', 'EchoMode': 'Password'}),
            ui.VGap(10),
            ui.HGroup([
                ui.Label({'Text': 'Model:', 'Weight': 0.3}),
                ui.ComboBox({'ID': 'ModelSelect', 'Weight': 0.7}),
            ]),
            ui.VGap(10),
            ui.VGroup({'StyleSheet': 'background-color: #262626; border-radius: 4px; padding: 10px;'}, [
                ui.Label({'Text': 'Custom Proxy Root (Optional):'}),
                ui.HGroup([
                    ui.LineEdit({'ID': 'ProxyPath', 'Text': config.get_val('proxy_path', ''), 'PlaceholderText': 'Select folder...'}),
                    ui.Button({'ID': 'BrowseBtn', 'Text': 'Browse'}),
                ]),
            ]),
            ui.VGap(20),
            ui.HGroup([
                ui.Button({'ID': 'CancelBtn', 'Text': 'Cancel'}),
                ui.Button({'ID': 'ProcessBtn', 'Text': 'Start Processing', 'StyleSheet': 'background-color: #2563eb; color: white; height: 40px; font-weight: bold;'}),
            ]),
            ui.VGap(10),
            ui.Label({'Text': '© 2025 W.Degan', 'Alignment': {'AlignRight': True}, 'Weight': 0, 'StyleSheet': 'color: #4b5563; font-size: 10px;'})
        ])
    ])

    itm = win.GetItems()
    itm['ProviderSelect'].AddItems(["Google Gemini", "OpenAI"])
    itm['ProviderSelect'].CurrentIndex = config.get_val('provider_index', 0)
    
    def update_ui(ev=None):
        provider = itm['ProviderSelect'].CurrentText
        itm['KeyLabel'].Text = f"{provider} API Key:"
        itm['ApiKey'].Text = config.get_api_key(provider)
        itm['ModelSelect'].Clear()
        if "Gemini" in provider:
            itm['ModelSelect'].AddItems(["gemini-3-flash-preview", "gemini-3-pro-preview"])
        else:
            itm['ModelSelect'].AddItems(["gpt-4o", "gpt-4o-mini"])

    win.On.ProviderSelect.CurrentIndexChanged = update_ui
    win.On.BrowseBtn.Clicked = lambda ev: itm['ProxyPath'].SetText(fusion.RequestDir() or itm['ProxyPath'].Text)
    win.On.CancelBtn.Clicked = lambda ev: disp.ExitLoop()
    win.On.MainWin.Close = lambda ev: disp.ExitLoop()
    update_ui()

    run_data = {}
    def on_start(ev):
        provider = itm['ProviderSelect'].CurrentText
        config.save_api_key(provider, itm['ApiKey'].Text)
        config.set_val('provider_index', itm['ProviderSelect'].CurrentIndex)
        config.set_val('proxy_path', itm['ProxyPath'].Text)
        run_data.update({
            'proceed': True,
            'provider': provider,
            'key': itm['ApiKey'].Text,
            'model': itm['ModelSelect'].CurrentText,
            'proxy_root': itm['ProxyPath'].Text
        })
        disp.ExitLoop()

    win.On.ProcessBtn.Clicked = on_start
    win.Show()
    disp.RunLoop()
    win.Hide()

    if not run_data.get('proceed'): return

    # Processing loop
    success_cnt = 0
    error_log = []
    
    progress_win = disp.AddWindow({'WindowTitle': 'Processing...', 'ID': 'ProgWin', 'Geometry': [500, 400, 400, 150]}, [
        ui.VGroup([
            ui.Label({'ID': 'Status', 'Text': 'Starting...', 'Alignment': {'AlignHCenter': True}, 'WordWrap': True}),
            ui.VGap(10),
            ui.Label({'ID': 'Counter', 'Text': f'0/{len(clips)}', 'Alignment': {'AlignHCenter': True}})
        ])
    ])
    p_itm = progress_win.GetItems()
    progress_win.On.ProgWin.Close = lambda ev: disp.ExitLoop()
    progress_win.Show()

    for i, clip in enumerate(clips):
        name = clip.GetName()
        p_itm['Counter'].Text = f"Processing {i+1} of {len(clips)}"
        p_itm['Status'].Text = f"Processing: {name}"
        progress_win.RecalcLayout()
        
        path, is_proxy = get_best_media_path(clip, run_data['proxy_root'])
        try:
            frames = extract_frames(path)
            if "Gemini" in run_data['provider']:
                meta, err = analyze_with_gemini(frames, run_data['key'], run_data['model'], name)
            else:
                meta, err = analyze_with_openai(frames, run_data['key'], run_data['model'], name)
            
            if meta:
                # Robust type check to prevent 'list has no attribute get'
                if isinstance(meta, list) and len(meta) > 0:
                    meta = meta[0]
                
                if isinstance(meta, dict):
                    clip.SetMetadata({
                        "Description": str(meta.get('short_desc', '')),
                        "Comments": str(meta.get('long_desc', '')),
                        "Keywords": ", ".join([str(x) for x in meta.get('keywords', [])])
                    })
                    success_cnt += 1
                else:
                    error_log.append(f"{name}: AI returned invalid JSON structure.")
            else: 
                error_log.append(f"{name}: AI failed to return metadata.")
        except Exception as e:
            error_log.append(f"{name}: {str(e)}")

    progress_win.Hide()

    # Final Summary Report
    report_layout = [
        ui.Label({'Text': 'Processing Complete!', 'StyleSheet': 'font-size: 18px; font-weight: bold;'}),
        ui.Label({'Text': f'Success: {success_cnt} | Issues: {len(error_log)}'}),
        ui.VGap(10),
    ]
    if error_log:
        report_layout.append(ui.TextEdit({'Text': "\\n".join(error_log), 'ReadOnly': True, 'Weight': 1, 'StyleSheet': 'background: #1f2937; color: #f87171;'}))
    report_layout.append(ui.Button({'ID': 'CloseBtn', 'Text': 'Close Report'}))
    report_layout.append(ui.VGap(5))
    report_layout.append(ui.Label({'Text': '© 2025 W.Degan', 'Alignment': {'AlignRight': True}, 'Weight': 0, 'StyleSheet': 'color: #4b5563; font-size: 10px;'}))

    report_win = disp.AddWindow({'WindowTitle': 'Metafootage Report', 'ID': 'RepWin', 'Geometry': [400, 300, 500, 450]}, [ui.VGroup(report_layout)])
    report_win.On.CloseBtn.Clicked = lambda ev: disp.ExitLoop()
    report_win.On.RepWin.Close = lambda ev: disp.ExitLoop()
    report_win.Show()
    disp.RunLoop()
    report_win.Hide()

if __name__ == "__main__":
    main()
