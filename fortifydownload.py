import os
import re
import sys
import json
import time
import errno
import shutil
import logging
from typing import Optional, Tuple, List, Dict

import requests
from requests.adapters import HTTPAdapter, Retry

# -------------------- CONFIG --------------------
SSC_URL       = os.getenv("SSC_URL", "https://fortify.yourdomain.com")
AUTH_TOKEN    = os.getenv("SSC_AUTH_TOKEN", "")      # <-- SSC API token
FILE_TOKEN    = os.getenv("SSC_FILE_TOKEN", "")      # <-- File Download Token (mat)
OUTPUT_ROOT   = os.getenv("SSC_OUTPUT_DIR", os.path.join(os.getcwd(), "fpr_downloads"))
VERIFY_SSL    = os.getenv("SSC_VERIFY_SSL", "false").lower() in ("1", "true", "yes")

# Choose how to pick "latest" version:
#   "max_id"  -> highest numeric id
#   "created" -> newest by 'created' timestamp
LATEST_STRATEGY = os.getenv("SSC_LATEST_STRATEGY", "max_id")  # "max_id" or "created"
# -------------------------------------------------

# Reduce "InsecureRequestWarning" noise if VERIFY_SSL is False
if not VERIFY_SSL:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

log = logging.getLogger("ssc_fpr")
log.setLevel(logging.INFO)
h = logging.StreamHandler(sys.stdout)
h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
log.addHandler(h)

def sanitize_path_component(name: str) -> str:
    """Make a string safe for filenames across OSes."""
    name = name.strip().replace("\\", "_").replace("/", "_").replace(":", "_")
    name = re.sub(r'[^a-zA-Z0-9._ -]+', "_", name)
    return re.sub(r'_+', "_", name)

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def ssc_session() -> requests.Session:
    sess = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    sess.mount("https://", HTTPAdapter(max_retries=retries))
    sess.mount("http://", HTTPAdapter(max_retries=retries))
    sess.headers.update({
        "Authorization": f"FortifyToken {AUTH_TOKEN}",
        "Accept": "application/json"
    })
    return sess

def ssc_get_json(sess: requests.Session, path: str, params: Dict[str, str] = None) -> Dict:
    url = f"{SSC_URL.rstrip('/')}{path}"
    resp = sess.get(url, params=params or {}, verify=VERIFY_SSL, timeout=30)
    if resp.status_code != 200:
        # Try to show helpful body beginning
        body = resp.text[:400].replace("\n", " ")
        raise RuntimeError(f"GET {path} -> HTTP {resp.status_code}. Body: {body}")
    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"GET {path} did not return JSON: {e}")

def find_project(sess: requests.Session, name: str) -> Optional[Dict]:
    """Exact case-insensitive match first. If none, return best 'contains' match or None."""
    data = ssc_get_json(sess, "/api/v1/projects", params={"start": 0, "limit": 1000, "fulltextsearch": "false"})
    projects = (data.get("data") or [])
    wanted = name.lower().strip()

    exact = [p for p in projects if (p.get("name") or "").lower().strip() == wanted]
    if exact:
        return exact[0]

    contains = [p for p in projects if wanted in (p.get("name") or "").lower()]
    if contains:
        # Return the first; also log alternatives
        log.warning(f"No exact project match for '{name}'. Close matches:")
        for p in contains[:10]:
            log.warning(f"  - {p.get('id')}  {p.get('name')}")
        return contains[0]

    return None

def pick_latest_version(versions: List[Dict]) -> Optional[Dict]:
    if not versions:
        return None
    if LATEST_STRATEGY == "created":
        # newest by created timestamp (string compare usually works for ISO8601; else convert)
        return sorted(versions, key=lambda v: v.get("created", ""), reverse=True)[0]
    # default: highest numeric id
    return sorted(versions, key=lambda v: int(v.get("id", 0)), reverse=True)[0]

def list_versions(sess: requests.Session, project_id: int) -> List[Dict]:
    data = ssc_get_json(sess, f"/api/v1/projects/{project_id}/versions", params={"start": 0, "limit": 700})
    return (data.get("data") or [])

def list_artifacts(sess: requests.Session, version_id: int) -> List[Dict]:
    data = ssc_get_json(sess, f"/api/v1/projectVersions/{version_id}/artifacts", params={"start": 0, "limit": 700})
    return (data.get("data") or [])

def download_artifact(sess: requests.Session, artifact_id: int, out_path: str) -> None:
    """Use the File Download Token (mat=) to download the artifact binary."""
    params = {"mat": FILE_TOKEN, "id": str(artifact_id)}
    url = f"{SSC_URL.rstrip('/')}/download/artifactDownload.html"
    with sess.get(url, params=params, verify=VERIFY_SSL, stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Download artifact {artifact_id} -> HTTP {r.status_code}")
        ensure_dir(os.path.dirname(out_path))
        with open(out_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)

def process_project(project_name: str) -> None:
    safe_name = sanitize_path_component(project_name)
    log.info(f"=== Project: {project_name} ===")

    if not AUTH_TOKEN:
        raise RuntimeError("SSC_AUTH_TOKEN is empty. Set a valid SSC API token.")
    if not FILE_TOKEN:
        raise RuntimeError("SSC_FILE_TOKEN is empty. Set a valid File Download Token.")
    if not SSC_URL.startswith("http"):
        raise RuntimeError("SSC_URL must start with http(s)://")

    sess = ssc_session()

    proj = find_project(sess, project_name)
    if not proj:
        log.error(f"Project '{project_name}' not found in SSC.")
        return
    project_id = proj.get("id")
    log.info(f"Project ID: {project_id}  Name: {proj.get('name')}")

    versions = list_versions(sess, project_id)
    if not versions:
        log.error(f"No versions for project id {project_id}")
        return

    latest = pick_latest_version(versions)
    if not latest:
        log.error("Could not determine latest version.")
        return
    version_id = latest.get("id")
    version_name = latest.get("name") or f"Version_{version_id}"
    log.info(f"Latest Version: {version_name} (id={version_id})")

    arts = list_artifacts(sess, version_id)
    fprs = [a for a in arts if (a.get("originalFileName") or "").lower().endswith(".fpr")]
    if not fprs:
        log.error(f"No FPR artifacts found for version id {version_id}")
        return

    # Create destination folder: <OUTPUT_ROOT>/<ProjectName>/<VersionName>/
    dest_dir = os.path.join(OUTPUT_ROOT, sanitize_path_component(proj.get("name") or safe_name),
                            sanitize_path_component(version_name))
    ensure_dir(dest_dir)

    for a in fprs:
        aid = a.get("id")
        oname = a.get("originalFileName") or f"Artifact_{aid}.fpr"
        out_file = os.path.join(dest_dir, sanitize_path_component(oname))
        log.info(f"Downloading artifact {aid}  ->  {out_file}")
        try:
            download_artifact(sess, aid, out_file)
        except Exception as e:
            log.error(f"Download failed for artifact {aid}: {e}")
        else:
            log.info(f"Saved: {out_file}")

def main(argv: List[str]):
    if len(argv) < 1:
        print("Usage:")
        print("  python download_latest_fpr.py \"Project A\" \"Project B\" ...")
        print("\nRequired env vars:")
        print("  SSC_URL, SSC_AUTH_TOKEN, SSC_FILE_TOKEN")
        print("Optional env vars:")
        print("  SSC_OUTPUT_DIR, SSC_VERIFY_SSL (true/false), SSC_LATEST_STRATEGY (max_id/created)")
        sys.exit(1)

    log.info(f"SSC_URL={SSC_URL}  VERIFY_SSL={VERIFY_SSL}  OUTPUT_DIR={OUTPUT_ROOT}")
    for name in argv:
        try:
            process_project(name)
        except Exception as e:
            log.error(f"Failed for '{name}': {e}")

if __name__ == "__main__":
    main(sys.argv[1:])
