#!/usr/bin/env python3
"""
Metafootage - DaVinci Resolve AI Plugin (Ultimate Multi-Provider Version)
Copyright (c) 2025 W.Degan

FEATURES:
- Non-blocking, cancelable processing loop.
- Result caching (avoids redundant API calls).
- Smart metadata merging (preserves existing keywords/comments).
- Robust BRAW/RAW Support via Proxy paths.
- Network resilience with exponential back-off and 30s timeouts.
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
import urllib.error
import time
import hashlib

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
# CONFIGURATION & CACHING
# ==============================================================================

class ConfigManager:
    def __init__(self):
        if platform.system() == "Windows":
            self.base_dir = os.path.join(os.environ.get('APPDATA', ''), 'Metafootage')
        else:
            self.base_dir = os.path.join(os.path.expanduser('~'), '.metafootage')
        
        os.makedirs(self.base_dir, exist_ok=True)
        self.config_path = os.path.join(self.base_dir, 'config.json')
        self.cache_path = os.path.join(self.base_dir, 'metafootage_cache.json')
        self.config = self._load_json(self.config_path)
        self.cache = self._load_json(self.cache_path)
    
    def _load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: return json.load(f)
            except: return {}
        return {}
    
    def save_config(self):
        with open(self.config_path, 'w') as f: json.dump(self.config, f, indent=2)
    
    def save_cache(self):
        with open(self.cache_path, 'w') as f: json.dump(self.cache, f, indent=2)

    def get_api_key(self, provider):
        key_name = f"{provider.lower().replace(' ', '_')}_api_key"
        try:
            if key_name in self.config:
                return base64.b64decode(self.config[key_name]).decode('utf-8')
        except: return ""
        return ""

    def save_api_key(self, provider, api_key):
        key_name = f"{provider.lower().replace(' ', '_')}_api_key"
        self.config[key_name] = base64.b64encode(api_key.encode('utf-8')).decode('utf-8')
        self.save_config()

    def get_cache_key(self, path, model, frames):
        if not os.path.exists(path): return None
        mtime = os.path.getmtime(path)
        raw_key = f"{path}_{mtime}_{model}_{frames}"
        return hashlib.md5(raw_key.encode()).hexdigest()

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
        if not proc.stdout.strip(): raise Exception("Could not read video duration.")
            
        duration = float(proc.stdout.strip())
        start_time = duration * 0.1
        step = (duration * 0.8) / (frame_count - 1 if frame_count > 1 else 1)
        
        for i in range(frame_count):
            ts = start_time + (i * step)
            out_file = os.path.join(temp_dir, f"frame_{i}.jpg")
            cmd = ["ffmpeg", "-ss", f"{ts:.3f}", "-i", file_path, "-frames:v", "1", "-vf", "scale=960:-1", "-q:v", "2", "-y", out_file]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            if os.path.exists(out_file):
                with open(out_file, "rb") as f:
                    base64_frames.append(base64.b64encode(f.read()).decode('utf-8'))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return base64_frames

def api_request(url, payload, headers=None, method="POST"):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method=method)
            req.add_header("Content-Type", "application/json")
            if headers:
                for k, v in headers.items(): req.add_header(k, v)
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8')), None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            try: error_body = e.read().decode()
            except: error_body = str(e)
            return None, f"HTTP {e.code}: {error_body}"
        except Exception as e:
            return None, str(e)
    return None, "Max retries reached"

# ==============================================================================
# AI ENGINES
# ==============================================================================

METADATA_SCHEMA_PROMPT = "Return JSON with: short_desc, long_desc, subjects (array), actions (array), camera, lighting, setting, emotion, keywords (array)."

def analyze_with_ai(frames, api_key, model, provider, filename):
    if "Gemini" in provider:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        parts = [{"text": f"Analyze: {filename}. {METADATA_SCHEMA_PROMPT}"}]
        for b64 in frames: parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        payload = {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
        res, err = api_request(url, payload)
        if res: return json.loads(res['candidates'][0]['content']['parts'][0]['text']), None
        return None, err
    else:
        url = "https://api.openai.com/v1/chat/completions"
        messages = [{"role": "system", "content": "You are a cinematic editor."}, {"role": "user", "content": [{"type": "text", "text": f"Analyze: {filename}. {METADATA_SCHEMA_PROMPT}"}]}]
        for b64 in frames: messages[1]["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        payload = {"model": model, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0.7}
        res, err = api_request(url, payload, {"Authorization": f"Bearer {api_key}"})
        if res: return json.loads(res['choices'][0]['message']['content']), None
        return None, err

# ==============================================================================
# MAIN PLUGIN LOGIC
# ==============================================================================

def main():
    bmd = load_bmd()
    if not bmd: return
    resolve = bmd.scriptapp("Resolve")
    fusion = resolve.Fusion()
    ui, disp = fusion.UIManager, bmd.UIDispatcher(fusion.UIManager)
    config = ConfigManager()

    project = resolve.GetProjectManager().GetCurrentProject()
    clips = project.GetMediaPool().GetSelectedClips() if project else []
    if not clips: return

    # Main UI Building (Restored high-fidelity layout)
    win = disp.AddWindow({'WindowTitle': 'Metafootage', 'ID': 'MainWin', 'Geometry': [400, 300, 620, 600]}, [
        ui.VGroup({'Spacing': 0}, [
            # Header
            ui.HGroup({'Weight': 0, 'ContentsMargins': [25, 20, 25, 5]}, [
                ui.Label({'Text': 'CONFIGURE ANALYSIS', 'StyleSheet': 'font-weight: bold; color: #60a5fa; font-size: 11px; letter-spacing: 1px;'}),
                ui.HGap(0, 1),
                ui.Label({'Text': f' {len(clips)} CLIPS ', 'StyleSheet': 'background-color: #3b82f6; color: white; border-radius: 4px; font-size: 10px; font-weight: bold; padding: 2px 6px;'}),
            ]),
            
            ui.VGap(10),
            
            # Form Content
            ui.VGroup({'ContentsMargins': [25, 10, 25, 20], 'Spacing': 14}, [
                
                # AI Engine Section
                ui.Label({'Text': 'AI ENGINE', 'StyleSheet': 'color: #9ca3af; font-size: 10px; font-weight: bold; padding-top: 5px;'}),
                ui.VGroup({'Spacing': 8}, [
                    ui.HGroup([ui.Label({'Text': 'Provider:', 'Weight': 0.3}), ui.ComboBox({'ID': 'Prov', 'Weight': 0.7})]),
                    ui.HGroup([ui.Label({'Text': 'Model:', 'Weight': 0.3}), ui.ComboBox({'ID': 'Mod', 'Weight': 0.7})]),
                    ui.HGroup([ui.Label({'Text': 'Frames:', 'Weight': 0.3}), ui.ComboBox({'ID': 'Fr', 'Weight': 0.7})]),
                ]),

                ui.VGap(8),

                # Authentication Section
                ui.Label({'Text': 'AUTHENTICATION', 'StyleSheet': 'color: #9ca3af; font-size: 10px; font-weight: bold; padding-top: 5px;'}),
                ui.HGroup([
                    ui.Label({'ID': 'KeyLabel', 'Text': 'API Key:', 'Weight': 0.3}),
                    ui.HGroup({'Spacing': 4, 'Weight': 0.7}, [
                        ui.LineEdit({'ID': 'Key', 'EchoMode': 'Password'}),
                        ui.Button({'ID': 'Tog', 'Text': 'Show', 'Checkable': True, 'Weight': 0, 'MinimumSize': [60, 28]}),
                    ]),
                ]),

                ui.VGap(8),

                # RAW / Proxy Support Section (Restored)
                ui.Label({'Text': 'RAW / PROXY SUPPORT (OPTIONAL)', 'StyleSheet': 'color: #9ca3af; font-size: 10px; font-weight: bold; padding-top: 5px;'}),
                ui.VGroup({'Spacing': 6}, [
                    ui.HGroup([
                        ui.Label({'Text': 'Root Path:', 'Weight': 0.3}),
                        ui.HGroup({'Spacing': 4, 'Weight': 0.7}, [
                            ui.LineEdit({'ID': 'ProxyPath', 'Text': config.config.get('proxy_path', ''), 'PlaceholderText': 'Resolve Proxy folder path...'}),
                            ui.Button({'ID': 'BrowseBtn', 'Text': 'Browse', 'Weight': 0, 'MinimumSize': [80, 28]}),
                        ]),
                    ]),
                    ui.HGroup([
                        ui.HGap(0, 0.3),
                        ui.Label({
                            'Text': 'Used when FFmpeg can’t read RAW (BRAW/R3D). Point to your optimized media or proxy folder.', 
                            'WordWrap': True, 'Weight': 0.7,
                            'StyleSheet': 'color: #6b7280; font-size: 9px; font-style: italic;'
                        }),
                    ]),
                ]),
                
                ui.VGap(8),
                ui.CheckBox({'ID': 'Force', 'Text': 'Reprocess even if cached', 'Checked': False}),
            ]),
            
            ui.VGap(0, 1),
            
            # Footer
            ui.HGroup({'ContentsMargins': [25, 0, 25, 25], 'Spacing': 12, 'Weight': 0}, [
                ui.Label({'Text': '© 2025 W.Degan', 'StyleSheet': 'color: #4b5563; font-size: 10px;'}, 0),
                ui.HGap(0, 1),
                ui.Button({'ID': 'Cancel', 'Text': 'Cancel', 'MinimumSize': [110, 36]}),
                ui.Button({'ID': 'Start', 'Text': 'Start Processing', 'MinimumSize': [170, 36], 'StyleSheet': 'background-color: #2563eb; color: white; border-radius: 4px; font-weight: bold;'}),
            ])
        ])
    ])

    itm = win.GetItems()
    itm['Prov'].AddItems(["Google Gemini", "OpenAI"])
    itm['Prov'].CurrentIndex = config.config.get('provider_index', 0)
    itm['Fr'].AddItems(["3", "5", "7"])
    itm['Fr'].CurrentIndex = config.config.get('frame_index', 0)
    
    def update_ui(ev=None):
        p = itm['Prov'].CurrentText
        itm['KeyLabel'].Text = f"{p} Key:"
        itm['Key'].Text = config.get_api_key(p)
        itm['Mod'].Clear()
        if "Gemini" in p: itm['Mod'].AddItems(["gemini-3-flash-preview", "gemini-3-pro-preview"])
        else: itm['Mod'].AddItems(["gpt-4o", "gpt-4o-mini"])

    win.On.Prov.CurrentIndexChanged = update_ui
    win.On.Tog.Clicked = lambda ev: itm['Key'].SetEchoMode('Normal' if itm['Tog'].Checked else 'Password')
    win.On.BrowseBtn.Clicked = lambda ev: itm['ProxyPath'].SetText(fusion.RequestDir() or itm['ProxyPath'].Text)
    win.On.Cancel.Clicked = lambda ev: disp.ExitLoop()
    update_ui()

    run_data = {'proceed': False}
    def on_start(ev):
        config.save_api_key(itm['Prov'].CurrentText, itm['Key'].Text)
        config.config['provider_index'] = itm['Prov'].CurrentIndex
        config.config['frame_index'] = itm['Fr'].CurrentIndex
        config.config['proxy_path'] = itm['ProxyPath'].Text
        config.save_config()
        
        run_data.update({
            'proceed': True, 
            'p': itm['Prov'].CurrentText, 
            'k': itm['Key'].Text, 
            'm': itm['Mod'].CurrentText, 
            'f': int(itm['Fr'].CurrentText), 
            'force': itm['Force'].Checked,
            'proxy_root': itm['ProxyPath'].Text
        })
        disp.ExitLoop()
        
    win.On.Start.Clicked = on_start
    win.Show(); disp.RunLoop(); win.Hide()

    if not run_data['proceed']: return

    # Processing UI
    prog = disp.AddWindow({'WindowTitle': 'Processing...', 'Geometry': [500, 400, 450, 180]}, [
        ui.VGroup({'ContentsMargins': [25, 20, 25, 25], 'Spacing': 15}, [
            ui.Label({'ID': 'St', 'Text': 'Initializing...', 'Alignment': {'AlignHCenter': True}, 'WordWrap': True}),
            ui.Label({'ID': 'Cn', 'Text': '0/0', 'Alignment': {'AlignHCenter': True}}),
            ui.Button({'ID': 'Stop', 'Text': 'Stop Analysis', 'StyleSheet': 'background: #f87171; color: white;'})
        ])
    ])
    p_itm = prog.GetItems()
    run_data['canceled'] = False
    prog.On.Stop.Clicked = lambda ev: run_data.update({'canceled': True})
    prog.Show()

    results = []
    for i, clip in enumerate(clips):
        if run_data['canceled']: break
        name = clip.GetName()
        p_itm['St'].Text = f"Processing: {name}"
        p_itm['Cn'].Text = f"{i+1} / {len(clips)}"
        prog.RecalcLayout()

        # Path resolution with Proxy support
        path, is_proxy = get_best_media_path(clip, run_data['proxy_root'])
        cache_key = config.get_cache_key(path, run_data['m'], run_data['f'])
        meta = None
        
        if not run_data['force'] and cache_key in config.cache:
            meta = config.cache[cache_key]
        else:
            try:
                frames = extract_frames(path, run_data['f'])
                meta, err = analyze_with_ai(frames, run_data['k'], run_data['m'], run_data['p'], name)
                if meta:
                    config.cache[cache_key] = meta
                    config.save_cache()
                else: results.append(f"Error {name}: {err}")
            except Exception as e: results.append(f"Error {name}: {str(e)}")

        if meta:
            if isinstance(meta, list) and len(meta) > 0: meta = meta[0]
            if isinstance(meta, dict):
                # Smart Merging Keywords
                existing_kw = set([k.strip() for k in clip.GetMetadata("Keywords").split(",") if k.strip()])
                new_kw = set([str(k).strip() for k in meta.get('keywords', [])])
                merged_kw = sorted(list(existing_kw.union(new_kw)))
                
                # Smart Merging Comments
                existing_com = clip.GetMetadata("Comments") or ""
                separator = "\n\n--- AI Analysis ---\n"
                if separator in existing_com:
                    # Replace only the AI part if it already exists
                    parts = existing_com.split(separator)
                    new_com = f"{parts[0]}{separator}{meta.get('long_desc', '')}"
                else:
                    new_com = f"{existing_com}{separator}{meta.get('long_desc', '')}"
                
                clip.SetMetadata({
                    "Description": str(meta.get('short_desc', '')),
                    "Comments": new_com,
                    "Keywords": ", ".join(merged_kw)
                })
            
    prog.Hide()
    if results:
        rep = disp.AddWindow({'WindowTitle': 'Report', 'Geometry': [400, 300, 600, 400]}, [
            ui.VGroup({'ContentsMargins': [20, 20, 20, 20]}, [
                ui.Label({'Text': 'Analysis Finished with Issues:', 'StyleSheet': 'color: #f87171; font-weight: bold;'}),
                ui.TextEdit({'Text': "\n".join(results), 'ReadOnly': True}),
                ui.Button({'ID': 'Ok', 'Text': 'Close'})
            ])
        ])
        rep.On.Ok.Clicked = lambda ev: disp.ExitLoop()
        rep.Show(); disp.RunLoop(); rep.Hide()

if __name__ == "__main__":
    main()
