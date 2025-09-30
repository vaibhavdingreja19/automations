# download_latest_fpr_hardcoded.py
# Python 3.x | requires: requests (pip install requests)

import os
import re
import sys
import shutil
from typing import List, Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

# ======== HARD-CODED CONFIG (EDIT THESE) ========
SSC_URL     = "https://fortify.yourdomain.com"   # <-- your SSC base URL
AUTH_TOKEN  = "PUT_SSC_API_TOKEN_HERE"           # <-- SSC API token (for REST calls)
FILE_TOKEN  = "PUT_FILE_DOWNLOAD_TOKEN_HERE"     # <-- File Download (mat) token for binary download
VERIFY_SSL  = False                               # set True if your cert is trusted
OUTPUT_DIR  = os.path.join(os.getcwd(), "fpr_downloads")

# How to decide "latest" version: "max_id" (highest numeric id) or "created" (newest timestamp)
LATEST_STRATEGY = "max_id"

# Multiple projects to process (exact SSC names work best)
PROJECTS = [
    "JH FINANCE IT : SERIATIM REPORTING APIP",
    # "Another App",
]
# ================================================

def sanitize(name: str) -> str:
    """Make a string safe for use in file/dir names."""
    name = name.strip().replace("\\", "_").replace("/", "_").replace(":", "_")
    name = re.sub(r'[^a-zA-Z0-9._ -]+', "_", name)
    return re.sub(r"_+", "_", name)

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "Authorization": f"FortifyToken {AUTH_TOKEN}",
        "Accept": "application/json",
    })
    return s

def get_json(s: requests.Session, path: str, params: Dict = None) -> Dict:
    url = f"{SSC_URL.rstrip('/')}{path}"
    r = s.get(url, params=(params or {}), verify=VERIFY_SSL, timeout=30)
    if r.status_code != 200:
        body = r.text[:400].replace("\n", " ")
        raise RuntimeError(f"GET {path} -> HTTP {r.status_code}. Body: {body}")
    try:
        return r.json()
    except Exception as e:
        raise RuntimeError(f"GET {path} did not return JSON: {e}")

def find_project(s: requests.Session, name: str) -> Optional[Dict]:
    """Exact case-insensitive match first; otherwise first 'contains' match (and print candidates)."""
    data = get_json(s, "/api/v1/projects", params={"start": 0, "limit": 1000, "fulltextsearch": "false"})
    projects = data.get("data") or []
    wanted = name.lower().strip()

    exact = [p for p in projects if (p.get("name") or "").lower().strip() == wanted]
    if exact:
        return exact[0]

    contains = [p for p in projects if wanted in (p.get("name") or "").lower()]
    if contains:
        print(f"[warn] No exact match for '{name}'. Close matches:")
        for p in contains[:10]:
            print(f"       - {p.get('id')}    {p.get('name')}")
        return contains[0]

    return None

def list_versions(s: requests.Session, project_id: int) -> List[Dict]:
    data = get_json(s, f"/api/v1/projects/{project_id}/versions", params={"start": 0, "limit": 700})
    return data.get("data") or []

def pick_latest(versions: List[Dict]) -> Optional[Dict]:
    if not versions:
        return None
    if LATEST_STRATEGY == "created":
        return sorted(versions, key=lambda v: v.get("created", ""), reverse=True)[0]
    return sorted(versions, key=lambda v: int(v.get("id", 0)), reverse=True)[0]

def list_artifacts(s: requests.Session, version_id: int) -> List[Dict]:
    data = get_json(s, f"/api/v1/projectVersions/{version_id}/artifacts", params={"start": 0, "limit": 700})
    return data.get("data") or []

def download_artifact(s: requests.Session, artifact_id: int, dest_path: str):
    """Use File Download Token (mat=) to download binary."""
    params = {"mat": FILE_TOKEN, "id": str(artifact_id)}
    url = f"{SSC_URL.rstrip('/')}/download/artifactDownload.html"
    with s.get(url, params=params, verify=VERIFY_SSL, stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Download artifact {artifact_id} -> HTTP {r.status_code}")
        ensure_dir(os.path.dirname(dest_path))
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)

def process_project(project_name: str):
    print(f"\n=== Project: {project_name} ===")
    if not AUTH_TOKEN:
        raise RuntimeError("AUTH_TOKEN is empty (needs SSC API token).")
    if not FILE_TOKEN:
        raise RuntimeError("FILE_TOKEN is empty (needs File Download token).")
    if not SSC_URL.startswith("http"):
        raise RuntimeError("SSC_URL must start with http(s)://")

    s = make_session()

    proj = find_project(s, project_name)
    if not proj:
        print(f"[error] Project not found: {project_name}")
        return
    pid = proj.get("id")
    pname = proj.get("name")
    print(f"Project ID: {pid}  Name: {pname}")

    versions = list_versions(s, pid)
    if not versions:
        print(f"[error] No versions for project id {pid}")
        return

    latest = pick_latest(versions)
    if not latest:
        print("[error] Could not determine latest version.")
        return

    vid = latest.get("id")
    vname = latest.get("name") or f"Version_{vid}"
    print(f"Latest Version: {vname} (id={vid})")

    arts = list_artifacts(s, vid)
    fprs = [a for a in arts if (a.get("originalFileName") or "").lower().endswith(".fpr")]
    if not fprs:
        print(f"[error] No FPR artifacts found for version id {vid}")
        return

    dest_dir = os.path.join(OUTPUT_DIR, sanitize(pname), sanitize(vname))
    ensure_dir(dest_dir)

    for a in fprs:
        aid = a.get("id")
        oname = a.get("originalFileName") or f"Artifact_{aid}.fpr"
        out_file = os.path.join(dest_dir, sanitize(oname))
        print(f"Downloading artifact {aid} -> {out_file}")
        try:
            download_artifact(s, aid, out_file)
        except Exception as e:
            print(f"[error] Failed: {e}")
        else:
            print(f"Saved: {out_file}")

def main():
    print(f"SSC_URL={SSC_URL}  VERIFY_SSL={VERIFY_SSL}  OUTPUT_DIR={OUTPUT_DIR}")
    for name in PROJECTS:
        try:
            process_project(name)
        except Exception as e:
            print(f"[error] '{name}': {e}")

if __name__ == "__main__":
    main()
