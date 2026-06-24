"""Streamlit Cloud entrypoint — Camberwell store (Melbourne, VIC).

Streamlit Community Cloud treats (repo, branch, main file) as ONE app, so each store needs
its own entrypoint file even though they run identical code. Point the Camberwell Streamlit
app at this file. Which store database it uses is decided entirely by THIS app's secrets
(SUPABASE_URL / SUPABASE_KEY) — not by the filename.
"""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(__file__), "app.py"), run_name="__main__")
