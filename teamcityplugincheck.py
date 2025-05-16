import os
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
import urllib3

# Disable SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CONFIG ===
TEAMCITY_URL = "https://teamcity.jhancock.com"
PAT_TOKEN = "your_actual_pat_token"
TEAMCITY_PLUGIN_DIR = "/opt/TeamCity/webapps/ROOT/WEB-INF/plugins"  # Update if different
TARGET_VERSION = "2023.11"

headers = {
    "Authorization": f"Bearer {PAT_TOKEN}",
    "Accept": "application/json"
}

def get_current_teamcity_version():
    url = f"{TEAMCITY_URL}/app/rest/server"
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            return response.json()["version"]
        else:
            print(f"Could not get TeamCity version: {response.status_code}")
            return "Unknown"
    except Exception as e:
        print(f"Error: {e}")
        return "Unknown"

def parse_plugin_meta(plugin_path):
    plugin_xml = os.path.join(plugin_path, "teamcity-plugin.xml")
    if not os.path.exists(plugin_xml):
        return None
    try:
        tree = ET.parse(plugin_xml)
        root = tree.getroot()
        name = root.findtext("info/name") or os.path.basename(plugin_path)
        vendor = root.findtext("info/vendor") or "Unknown"
        compat = root.findtext("requirements/teamcity") or "Unknown"
        return {
            "Plugin Name": name,
            "Vendor": vendor,
            "Compatible Versions": compat,
            "Path": plugin_path
        }
    except Exception as e:
        return {
            "Plugin Name": os.path.basename(plugin_path),
            "Vendor": "Parse Error",
            "Compatible Versions": str(e),
            "Path": plugin_path
        }

def is_compatible(compat_str, target_version):
    if compat_str in ["Unknown", None]:
        return "Unknown"
    return "Yes" if target_version in compat_str else "No"

def check_plugins(target_version):
    plugin_data = []
    for plugin_name in os.listdir(TEAMCITY_PLUGIN_DIR):
        plugin_path = os.path.join(TEAMCITY_PLUGIN_DIR, plugin_name)
        if os.path.isdir(plugin_path):
            info = parse_plugin_meta(plugin_path)
            if info:
                info["Compatible with Target Version?"] = is_compatible(info["Compatible Versions"], target_version)
                plugin_data.append(info)
    return plugin_data

def main():
    current_version = get_current_teamcity_version()
    print(f"Current TeamCity Version: {current_version}")
    print(f"Checking plugin compatibility with target version: {TARGET_VERSION}")

    plugin_report = check_plugins(TARGET_VERSION)
    df = pd.DataFrame(plugin_report)

    filename = f"teamcity_plugin_compatibility_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False)
    print(f"Report saved to: {filename}")

if __name__ == "__main__":
    main()
