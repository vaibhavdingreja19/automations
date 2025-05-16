import os
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
import zipfile
import urllib3
import requests

# === CONFIG ===
TEAMCITY_URL = "http://localhost:8111"
PAT_TOKEN = "your_pat_token_here"
TEAMCITY_PLUGIN_DIR = "E:\\TeamCity\\webapps\\ROOT\\WEB-INF\\plugins"  # Adjust as needed
TARGET_VERSION = "2023.11"

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

headers = {
    "Authorization": f"Bearer {PAT_TOKEN}",
    "Accept": "application/json"
}


def get_current_teamcity_version():
    try:
        resp = requests.get(f"{TEAMCITY_URL}/app/rest/server", headers=headers, verify=False)
        if resp.status_code == 200:
            return resp.json().get("version", "Unknown")
        else:
            print(f"Failed to get TeamCity version: {resp.status_code} - {resp.text}")
            return "Unknown"
    except Exception as e:
        print(f"Error: {e}")
        return "Unknown"


def extract_from_xml(xml_path, version_xpath="version"):
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        version = root.findtext(version_xpath) or "Unknown"
        return version.strip()
    except Exception:
        return None


def extract_from_zip(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for candidate in ["META-INF/plugin.xml", "teamcity-plugin.xml"]:
                if candidate in z.namelist():
                    with z.open(candidate) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        version = root.findtext("version") or root.findtext("info/version")
                        if version:
                            return version.strip()
    except Exception:
        return None


def parse_plugin_folder(plugin_path):
    plugin_name = os.path.basename(plugin_path)
    version = None

    # 1. teamcity-plugin.xml
    tc_plugin = os.path.join(plugin_path, "teamcity-plugin.xml")
    if os.path.exists(tc_plugin):
        version = extract_from_xml(tc_plugin, "version")

    # 2. plugin-info.xml
    if not version or version == "Unknown":
        pi_xml = os.path.join(plugin_path, "plugin-info.xml")
        if os.path.exists(pi_xml):
            version = extract_from_xml(pi_xml, "version")

    # 3. Inside zip or jar
    if not version or version == "Unknown":
        for f in os.listdir(plugin_path):
            if f.endswith(".zip") or f.endswith(".jar"):
                version = extract_from_zip(os.path.join(plugin_path, f))
                if version:
                    break

    return {
        "Plugin Name": plugin_name,
        "Plugin Version": version or "Unknown",
        "Path": plugin_path
    }


def check_plugins():
    plugin_data = []
    for plugin in os.listdir(TEAMCITY_PLUGIN_DIR):
        plugin_path = os.path.join(TEAMCITY_PLUGIN_DIR, plugin)
        if os.path.isdir(plugin_path):
            plugin_data.append(parse_plugin_folder(plugin_path))
    return plugin_data


def main():
    current_version = get_current_teamcity_version()
    print(f"Detected TeamCity version: {current_version}")
    print(f"Scanning plugins in: {TEAMCITY_PLUGIN_DIR}")

    plugins = check_plugins()
    df = pd.DataFrame(plugins)

    filename = f"teamcity_plugins_fullscan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False)
    print(f"\nPlugin report saved as: {filename}")


if __name__ == "__main__":
    main()
