METAFOOTAGE
AI-powered metadata generation for DaVinci Resolve

Metafootage is a single-file DaVinci Resolve scripting plugin that uses
Google Gemini or OpenAI to analyze video clips and automatically generate
rich, editorially useful metadata.

It is designed to save time on long-form projects by turning raw footage
into searchable, human-readable clips without changing your editing workflow.

WHAT METAFOOTAGE DOES

Select clips in the Media Pool → run Metafootage → it:

Extracts representative frames from each clip

Sends those frames to your chosen AI model

Generates cinematic descriptions (action, setting, lighting, camera feel)

Writes results directly into Resolve’s metadata fields

Merges with existing keywords instead of overwriting them

The output is meant to help editors FIND and UNDERSTAND footage faster,
not just label it.

KEY FEATURES

CINEMATIC DESCRIPTIONS
Metadata is written in natural language, focused on what’s happening in the
shot and how it looks and feels — useful during real editorial decisions.

ADJUSTABLE FRAME SAMPLING
Choose how many frames per clip are analyzed (3, 5, or 7) to balance speed,
cost, and descriptive depth.

SMART KEYWORD HANDLING
Existing keywords are preserved and merged with new ones so prior
organization is never destroyed.

MODEL SELECTION
Use a faster model for bulk logging or a higher-quality model for important
or hero moments.

RAW-FRIENDLY VIA PROXIES
Some camera RAW formats (BRAW, R3D, ARRIRAW) can’t be reliably decoded by
FFmpeg. Metafootage supports this by analyzing Resolve proxy or optimized
media instead when needed.

LOCAL-FIRST
All processing runs from your machine. Media is not stored by Metafootage
beyond what’s required to send a request to your AI provider.

REQUIREMENTS

DaVinci Resolve (Studio or Free)

Python (used by Resolve scripting)

FFmpeg (used to extract frames)

Google Gemini API key OR OpenAI API key

INSTALLING FFMPEG

Windows:
winget install ffmpeg

macOS:
brew install ffmpeg

Linux (example):
sudo apt install ffmpeg

INSTALLATION (DAVINCI RESOLVE)

Metafootage is distributed as a SINGLE SCRIPT FILE.

Copy Metafootage.py to your Resolve Scripts folder:

Windows:
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\

macOS:
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/

Linux:
/opt/resolve/Fusion/Scripts/Edit/

Restart DaVinci Resolve.

Select one or more clips in the Media Pool.

Run:
Workspace → Scripts → Metafootage

On first run, enter your Gemini or OpenAI API key.

API KEY STORAGE

API keys are stored locally on your machine in a small config file.
They are base64-encoded for light obfuscation (not encryption).

Metafootage does NOT transmit or store API keys anywhere else.

FILES IN THIS REPOSITORY

Metafootage.py
The Resolve script. This is the only file required to run Metafootage.

README.txt
Installation and usage instructions.

LICENSE
MIT License.

CONTRIBUTING

If this tool saved you time, contributions and improvements are welcome,
but never expected.

LICENSE

Released under the MIT License.
See the LICENSE file for details.