"""Streamlit Cloud entrypoint — Pagewood store.

Streamlit Community Cloud treats (repo, branch, main file) as ONE app, so each store needs
its own entrypoint file even though they run identical code. Point the Pagewood Streamlit
app at this file. Which store database it uses is decided entirely by THIS app's secrets
(SUPABASE_URL / SUPABASE_KEY) — not by the filename.

To add another store: copy this file to <Store>.py and deploy a new app from it.
"""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(__file__), "app.py"), run_name="__main__")
