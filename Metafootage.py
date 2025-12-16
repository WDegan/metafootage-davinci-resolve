#!/usr/bin/env python3
"""
Metafootage - DaVinci Resolve AI Plugin
Copyright (c) 2025 W.Degan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

FEATURES:
- Cinematic Analysis: Lighting, Camera Movement, Emotion, Subject detection.
- Smart Keyword Merging: Preserves your existing organization.
- Dual Model Support: Switch between Speed (Flash) and Quality (Pro).
- Proxy-Aware: Automatically handles BRAW/RED footage via proxies.
- Robust: Retry logic and connection handling.

INSTALLATION:
1. Windows: Copy this file to %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\
2. Mac: Copy this file to ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/
3. Linux: Copy this file to /opt/resolve/Fusion/Scripts/Edit/

USAGE:
1. Open DaVinci Resolve -> Edit Page
2. Select clips in Media Pool
3. Workspace > Scripts > Metafootage
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
    """Safely load the DaVinciResolveScript module"""
    try:
        import DaVinciResolveScript as bmd
        return bmd
    except ImportError:
        # Define default paths based on OS with raw strings for Windows
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
    
    def save_api_key(self, api_key):
        self.config['api_key'] = base64.b64encode(api_key.encode('utf-8')).decode('utf-8')
        self._save_config()
    
    def get_api_key(self):
        try:
            if 'api_key' in self.config:
                return base64.b64decode(self.config['api_key']).decode('utf-8')
        except:
            return ""
        return ""
    
    def get_frame_count(self):
        return self.config.get('frame_count', 5)
    
    def set_frame_count(self, count):
        self.config['frame_count'] = count
        self._save_config()
        
    def get_model_index(self):
        return self.config.get('model_index', 0)
        
    def set_model_index(self, index):
        self.config['model_index'] = index
        self._save_config()

    def get_proxy_path(self):
        return self.config.get('proxy_path', '')

    def set_proxy_path(self, path):
        self.config['proxy_path'] = path
        self._save_config()

# ==============================================================================
# VIDEO PROCESSING
# ==============================================================================

def get_ffmpeg_cmd():
    return "ffmpeg"

def get_ffprobe_cmd():
    return "ffprobe"

def extract_frames(file_path, frame_count=5):
    """Extracts frames using local FFmpeg. Returns base64 list."""
    
    if not os.path.exists(file_path):
        raise Exception(f"File not found: {file_path}")

    temp_dir = tempfile.mkdtemp(prefix="metafootage_")
    base64_frames = []

    try:
        # Get duration using ffprobe
        cmd_dur = [get_ffprobe_cmd(), "-v", "error", "-show_entries", "format=duration", 
                  "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            proc = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                text=True, startupinfo=startupinfo)
        except FileNotFoundError:
            raise Exception("FFprobe not found. Please install FFmpeg.")

        if proc.returncode != 0:
            raise Exception(f"FFprobe error: {proc.stderr}")
            
        try:
            duration = float(proc.stdout.strip())
        except ValueError:
            raise Exception("Could not determine video duration.")
        
        start_time = duration * 0.1
        end_time = duration * 0.9
        if frame_count > 1:
            step = (end_time - start_time) / (frame_count - 1)
        else:
            step = 0
            start_time = duration / 2
        
        for i in range(frame_count):
            ts = start_time + (i * step)
            out_file = os.path.join(temp_dir, f"frame_{i}.jpg")
            
            # Extract frame at 960px width, quality 2
            cmd = [
                get_ffmpeg_cmd(), "-ss", f"{ts:.3f}", "-i", file_path,
                "-frames:v", "1", "-vf", "scale=960:-1", "-q:v", "2", "-y", out_file
            ]
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            
            # Validation: Check if file exists AND is not empty (ffmpeg often creates 0-byte files on error)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 1024:
                with open(out_file, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                    base64_frames.append(b64)
            else:
                pass

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    if not base64_frames:
        raise Exception("Failed to extract any valid frames. File might be corrupt or unsupported.")

    return base64_frames

# ==============================================================================
# GEMINI API
# ==============================================================================

def make_request_with_retry(req, retries=3):
    """Retries request with exponential backoff"""
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.loads(response.read().decode('utf-8')), None
        except Exception as e:
            if i == retries - 1:
                return None, str(e)
            time.sleep((i + 1) * 2 + random.uniform(0, 1))
    return None, "Unknown error"

def analyze_with_gemini(frames, api_key, model_name, filename):
    """Calls Google Gemini API via REST"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "shot_id": {"type": "STRING", "description": "The filename or ID of the shot"},
            "short_desc": {"type": "STRING", "description": "Brief one-sentence description (max 100 chars)"},
            "long_desc": {"type": "STRING", "description": "Detailed paragraph describing the shot, camera work, and story potential"},
            "subjects": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "List of visible subjects"},
            "actions": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "List of actions or movements"},
            "camera": {"type": "STRING", "description": "Camera movement and framing description"},
            "lighting": {"type": "STRING", "description": "Lighting quality and characteristics"},
            "setting": {"type": "STRING", "description": "Location and environment description"},
            "emotion": {"type": "STRING", "description": "Emotional tone and mood"},
            "keywords": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Searchable keywords for this shot"},
        },
        "required": ["short_desc", "long_desc", "subjects", "actions", "camera", "lighting", "setting", "emotion", "keywords"]
    }

    system_instruction = """You are a professional cinematic video editor generating metadata for footage management.
    You will view a series of frames from a single continuous video shot.
    IMPORTANT: The footage may be in a flat Log color profile. Ignore low contrast or 'washed out' looks. Focus on content, composition, and action.
    Be specific, cinematic, and editor-focused in your descriptions."""

    content_parts = []
    content_parts.append({"text": f"Analyze these frames from video file: {filename}."})
    
    for b64 in frames:
        content_parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64
            }
        })

    payload = {
        "contents": [{"parts": content_parts}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.7
        }
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    
    result, error = make_request_with_retry(req)
    
    if error:
        return None, f"API Error: {error}"
        
    if 'candidates' in result and result['candidates']:
        candidate = result['candidates'][0]
        if 'content' in candidate and 'parts' in candidate['content']:
            text_resp = candidate['content']['parts'][0]['text']
            return json.loads(text_resp), None
        else:
            return None, "Unexpected API response structure"
    else:
        return None, "No candidates returned"

# ==============================================================================
# UI & MAIN LOGIC
# ==============================================================================

def write_metadata_smart(clip, metadata):
    """Writes metadata, merging tags instead of overwriting"""
    try:
        # Build description
        comments_parts = []
        if metadata.get('long_desc'):
            comments_parts.append(metadata['long_desc'])
        if metadata.get('lighting'):
            comments_parts.append(f"\n\nLighting: {metadata['lighting']}")
        if metadata.get('emotion'):
            comments_parts.append(f"Emotion: {metadata['emotion']}")
        comments = ''.join(comments_parts)
        
        # Merge Keywords
        new_keywords = []
        for field in ['keywords', 'subjects', 'actions']:
            if metadata.get(field):
                new_keywords.extend(metadata[field])
        
        # Get existing keywords
        existing_kw_str = clip.GetMetadata("Keywords")
        current_keywords = set()
        if existing_kw_str:
            for k in existing_kw_str.split(','):
                k = k.strip()
                if k: current_keywords.add(k)
        
        # Add new unique keywords
        for k in new_keywords:
            if k: current_keywords.add(k)
            
        final_keywords = ", ".join(sorted(list(current_keywords)))
        
        metadata_dict = {}
        if metadata.get('short_desc'):
            metadata_dict['Description'] = metadata['short_desc']
        if comments:
            metadata_dict['Comments'] = comments
        if metadata.get('camera'):
            metadata_dict['Shot'] = metadata['camera']
        if metadata.get('setting'):
            metadata_dict['Scene'] = metadata['setting']
        if final_keywords:
            metadata_dict['Keywords'] = final_keywords
        
        if metadata_dict:
            clip.SetMetadata(metadata_dict)
            return True
        return False
    except Exception as e:
        print(f"Metadata write error: {e}")
        return False

def find_manual_proxy(source_path, custom_root=None):
    """
    Search for proxies in common locations if Resolve API fails.
    Returns: (path, debug_locations_list)
    """
    if not source_path: return None, []
    
    folder = os.path.dirname(source_path)
    filename = os.path.basename(source_path)
    name_no_ext = os.path.splitext(filename)[0]
    
    candidates = []
    
    # 1. Custom Root Logic (If provided by user)
    if custom_root and os.path.exists(custom_root):
        # Direct file check (F:/clip.mov)
        candidates.append(os.path.join(custom_root, f"{name_no_ext}.mov"))
        candidates.append(os.path.join(custom_root, f"{name_no_ext}.mp4"))
        candidates.append(os.path.join(custom_root, filename))
        
        # Proxy Subfolders in Custom Root (F:/Proxy/clip.mov)
        candidates.append(os.path.join(custom_root, "Proxy", f"{name_no_ext}.mov"))
        candidates.append(os.path.join(custom_root, "Proxies", f"{name_no_ext}.mov"))
        candidates.append(os.path.join(custom_root, "Proxy", filename))

    # 2. Relative Logic (Standard Source Folder)
    candidates.append(os.path.join(folder, "Proxy", f"{name_no_ext}.mov"))
    candidates.append(os.path.join(folder, "Proxy", f"{name_no_ext}.mp4"))
    candidates.append(os.path.join(folder, "Proxies", f"{name_no_ext}.mov"))
    candidates.append(os.path.join(folder, "Proxies", f"{name_no_ext}.mp4"))
    
    checked_locs = []
    
    for c in candidates:
        checked_locs.append(c)
        if os.path.exists(c):
            return c, checked_locs
            
    return None, checked_locs

def main():
    bmd = load_bmd()
    if not bmd:
        print("ERROR: DaVinciResolveScript module not found.")
        return

    resolve = bmd.scriptapp("Resolve")
    if not resolve: return

    fusion = resolve.Fusion()
    ui = fusion.UIManager
    disp = bmd.UIDispatcher(ui)
    config = ConfigManager()

    project = resolve.GetProjectManager().GetCurrentProject()
    mediapool = project.GetMediaPool() if project else None
    
    if not mediapool:
        print("No project open.")
        return

    clips = mediapool.GetSelectedClips()
    if not clips:
        win = disp.AddWindow({'WindowTitle': 'Metafootage', 'Geometry': [400, 300, 300, 100]}, [
            ui.VGroup([
                ui.Label({'Text': 'Please select clips in the Media Pool first.', 'Alignment': {'AlignHCenter': True}}),
                ui.VGap(10),
                ui.Button({'ID': 'CloseBtn', 'Text': 'Close'})
            ])
        ])
        win.On.CloseBtn.Clicked = lambda ev: disp.ExitLoop()
        win.Show()
        disp.RunLoop()
        win.Hide()
        return

    # Main Dialog
    win = disp.AddWindow({
        'WindowTitle': 'Metafootage - AI Metadata',
        'ID': 'MainWin',
        'Geometry': [400, 300, 500, 560],
    }, [
        ui.VGroup([
            # Header
            ui.HGroup({'Weight': 0}, [
                ui.Label({'Text': 'Metafootage', 'Weight': 1, 'StyleSheet': 'font-size: 20px; font-weight: bold; color: #60a5fa;'}),
            ]),
            ui.VGap(2),
            ui.Label({'Text': f'Selected Clips: {len(clips)}', 'Weight': 0, 'StyleSheet': 'color: #9ca3af;'}),
            ui.VGap(15),
            
            # API Key
            ui.Label({'Text': 'Google Gemini API Key:', 'Weight': 0}),
            ui.LineEdit({
                'ID': 'ApiKey', 
                'Text': config.get_api_key(), 
                'EchoMode': 'Password',
                'PlaceholderText': 'Paste key here'
            }),
            ui.VGap(10),
            
            # Settings Group
            ui.VGroup({'Weight': 0, 'StyleSheet': 'background-color: #262626; border-radius: 4px; padding: 10px;'}, [
                 ui.HGroup({'Weight': 0}, [
                    ui.Label({'Text': 'AI Model:', 'Weight': 0.4}),
                    ui.ComboBox({'ID': 'ModelSelect', 'Weight': 0.6}),
                ]),
                ui.VGap(5),
                ui.HGroup({'Weight': 0}, [
                    ui.Label({'Text': 'Frame Count:', 'Weight': 0.4}),
                    ui.ComboBox({'ID': 'FrameCount', 'Weight': 0.6}),
                ]),
                ui.VGap(10),
                ui.Label({'Text': 'Note: "Quality" model (Gemini 3 Pro) is better for complex scenes.', 'StyleSheet': 'color: #6b7280; font-size: 11px;', 'WordWrap': True}),
            ]),

            ui.VGap(10),

            # Proxy Settings
            ui.VGroup({'Weight': 0, 'StyleSheet': 'background-color: #262626; border-radius: 4px; padding: 10px;'}, [
                ui.Label({'Text': 'Custom Proxy Location (Optional):', 'Weight': 0}),
                ui.Label({'Text': 'Use this if your proxies are on a separate drive (e.g. F:/Proxies)', 'StyleSheet': 'color: #9ca3af; font-size: 10px;'}),
                ui.HGroup({'Weight': 0}, [
                    ui.LineEdit({'ID': 'ProxyPath', 'Text': config.get_proxy_path(), 'PlaceholderText': 'Select folder...', 'Weight': 1}),
                    ui.Button({'ID': 'BrowseBtn', 'Text': 'Browse', 'Weight': 0}),
                ]),
            ]),
            
            ui.VGap(20),
            
            # Buttons
            ui.HGroup({'Weight': 0}, [
                ui.Button({'ID': 'CancelBtn', 'Text': 'Cancel', 'Weight': 0, 'StyleSheet': 'min-width: 80px;'}),
                ui.HGap(10),
                ui.Button({'ID': 'ProcessBtn', 'Text': 'Start Processing', 'Weight': 1, 'StyleSheet': 'background-color: #2563eb; color: white; font-weight: bold;'}),
            ]),
            
            ui.VGap(10),
            
            # Footer
            ui.Label({
                'Text': '© 2025 W.Degan', 
                'Alignment': {'AlignRight': True}, 
                'Weight': 0, 
                'StyleSheet': 'color: #4b5563; font-size: 10px;'
            })
        ]),
    ])
    
    itm = win.GetItems()
    
    # Init Dropdowns
    itm['ModelSelect'].AddItem("Gemini 2.5 Flash (Speed)")
    itm['ModelSelect'].AddItem("Gemini 3.0 Pro (Quality)")
    itm['ModelSelect'].CurrentIndex = config.get_model_index()

    itm['FrameCount'].AddItem("3 frames")
    itm['FrameCount'].AddItem("5 frames")
    itm['FrameCount'].AddItem("7 frames")
    
    # Restore saved frame count
    saved_fc = config.get_frame_count()
    if saved_fc == 3: itm['FrameCount'].CurrentIndex = 0
    elif saved_fc == 7: itm['FrameCount'].CurrentIndex = 2
    else: itm['FrameCount'].CurrentIndex = 1

    result_data = {}

    def on_browse(ev):
        # Resolve Fusion's RequestDir might vary by version/OS
        try:
            path = fusion.RequestDir()
            if path:
                itm['ProxyPath'].Text = path
        except:
            pass

    def on_process(ev):
        key = itm['ApiKey'].Text.strip()
        if not key.startswith('AI'):
            if len(key) < 10:
                print("Invalid Key")
                return
        
        config.save_api_key(key)
        
        m_idx = itm['ModelSelect'].CurrentIndex
        config.set_model_index(m_idx)
        model_name = "gemini-3-pro-preview" if m_idx == 1 else "gemini-2.5-flash"
        
        fc_idx = itm['FrameCount'].CurrentIndex
        frame_count = [3, 5, 7][fc_idx]
        config.set_frame_count(frame_count)
        
        proxy_path_in = itm['ProxyPath'].Text.strip()
        config.set_proxy_path(proxy_path_in)
        
        result_data['key'] = key
        result_data['model'] = model_name
        result_data['frames'] = frame_count
        result_data['proxy_root'] = proxy_path_in
        result_data['proceed'] = True
        disp.ExitLoop()

    win.On.ProcessBtn.Clicked = on_process
    win.On.BrowseBtn.Clicked = on_browse
    win.On.CancelBtn.Clicked = lambda ev: disp.ExitLoop()
    win.On.MainWin.Close = lambda ev: disp.ExitLoop()
    
    win.Show()
    disp.RunLoop()
    win.Hide()
    
    if not result_data.get('proceed'):
        return

    # Processing Loop
    progress_win = disp.AddWindow({
        'WindowTitle': 'Processing', 
        'ID': 'ProgressWin',
        'Geometry': [400, 300, 400, 150]
    }, [
        ui.VGroup([
            ui.Label({'ID': 'Status', 'Text': 'Initializing...', 'Alignment': {'AlignHCenter': True}, 'WordWrap': True}),
            ui.VGap(10),
            ui.Label({'ID': 'Counter', 'Text': '0/0', 'Alignment': {'AlignHCenter': True}})
        ])
    ])
    p_itm = progress_win.GetItems()
    progress_win.Show()

    success_cnt = 0
    total = len(clips)
    error_log = []

    for i, clip in enumerate(clips):
        name = clip.GetName()
        p_itm['Counter'].Text = f"Processing clip {i+1} of {total}"
        p_itm['Status'].Text = f"Extracting frames for: {name}"
        progress_win.RecalcLayout()
        
        # 1. Get File Path
        file_path = clip.GetClipProperty("File Path")
        
        # 2. Check for Proxy if RAW
        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        is_raw = ext in ['.braw', '.r3d', '.ari', '.dng', '.crm']
        
        used_proxy = False
        
        if is_raw:
            # Method A: Resolve API
            proxy_path = clip.GetClipProperty("Proxy Path")
            
            # Method B: Manual Search (Includes Custom Root)
            if not proxy_path:
                found_proxy, checked_locs = find_manual_proxy(file_path, result_data.get('proxy_root'))
                if found_proxy:
                    proxy_path = found_proxy
            
            if proxy_path and os.path.exists(proxy_path):
                file_path = proxy_path
                used_proxy = True
            else:
                # Fail immediately for RAW without proxy
                locs_debug = "\n".join(checked_locs) if 'checked_locs' in locals() else "Standard Resolve API check"
                msg = f"{name}: Skipped (BRAW/RAW). No proxy found.\nChecked locations:\n{locs_debug}"
                print(msg)
                error_log.append(msg)
                p_itm['Status'].Text = f"Skipped {name} (No Proxy)"
                continue

        if not file_path or not os.path.exists(file_path):
            msg = f"{name}: Skipped. Source file not found on disk."
            print(msg)
            error_log.append(msg)
            continue

        try:
            frames = extract_frames(file_path, result_data['frames'])
            
            p_itm['Status'].Text = f"Analyzing {name} with AI..."
            progress_win.RecalcLayout()
            
            metadata, err = analyze_with_gemini(frames, result_data['key'], result_data['model'], name)
            
            if metadata:
                write_metadata_smart(clip, metadata)
                success_cnt += 1
            else:
                msg = f"{name}: Analysis failed. {err}"
                print(msg)
                error_log.append(msg)
                
        except Exception as e:
            msg = f"{name}: Error. {str(e)}"
            print(msg)
            error_log.append(msg)
            p_itm['Status'].Text = "Error occurred"
            
    progress_win.Hide()
    print(f"Done. Processed {success_cnt}/{total} clips.")
    
    # Show Final Summary with Errors
    result_layout = [
        ui.Label({'Text': 'Processing Complete!', 'Alignment': {'AlignHCenter': True}, 'StyleSheet': 'font-weight: bold; font-size: 16px;'}),
        ui.VGap(10),
        ui.HGroup({'Weight': 0}, [
            ui.Label({'Text': f'Success: {success_cnt}', 'StyleSheet': 'color: #22c55e; font-weight: bold;'}),
            ui.HGap(20),
            ui.Label({'Text': f'Issues: {len(error_log)}', 'StyleSheet': 'color: #ef4444; font-weight: bold;' if error_log else 'color: #9ca3af;'}),
        ]),
        ui.VGap(10),
    ]

    if error_log:
        result_layout.append(ui.Label({'Text': 'Issues Report:', 'Weight': 0}))
        result_layout.append(ui.TextEdit({'Text': "\n".join(error_log), 'ReadOnly': True, 'Weight': 1, 'StyleSheet': 'font-family: monospace; font-size: 11px; background: #1f2937; color: #f87171;'}))
    else:
        result_layout.append(ui.Label({'Text': 'All clips processed successfully.', 'Alignment': {'AlignHCenter': True}, 'Weight': 1}))

    result_layout.append(ui.VGap(10))
    result_layout.append(ui.Button({'ID': 'OkBtn', 'Text': 'Close', 'Weight': 0}))
    result_layout.append(ui.VGap(5))
    result_layout.append(ui.Label({'Text': '© 2025 W.Degan', 'Alignment': {'AlignRight': True}, 'Weight': 0, 'StyleSheet': 'color: #4b5563; font-size: 10px;'}))

    res_win = disp.AddWindow({
        'WindowTitle': 'Processing Report', 
        'ID': 'ResultWin',
        'Geometry': [400, 300, 600, 500]
    }, [
        ui.VGroup(result_layout)
    ])
    
    res_win.On.OkBtn.Clicked = lambda ev: disp.ExitLoop()
    res_win.On.ResultWin.Close = lambda ev: disp.ExitLoop()
    res_win.Show()
    disp.RunLoop()
    res_win.Hide()

if __name__ == "__main__":
    main()
