import os
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

# === CONFIG ===
TEAMCITY_PLUGIN_DIR = "E:\\TeamCity\\webapps\\ROOT\\WEB-INF\\plugins"  # Adjust path if needed

def parse_teamcity_plugin(plugin_path):
    xml_path = os.path.join(plugin_path, "teamcity-plugin.xml")
    plugin_folder_name = os.path.basename(plugin_path)

    if not os.path.exists(xml_path):
        return {
            "Plugin Folder": plugin_folder_name,
            "Plugin Name": "Not Found",
            "Plugin Version": "Not Found",
            "Vendor": "Not Found"
        }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        name = root.findtext("info/name") or plugin_folder_name
        version = root.findtext("info/version") or "Unknown"
        vendor = root.findtext("info/vendor/name") or "Unknown"

        return {
            "Plugin Folder": plugin_folder_name,
            "Plugin Name": name.strip(),
            "Plugin Version": version.strip(),
            "Vendor": vendor.strip()
        }
    except Exception as e:
        return {
            "Plugin Folder": plugin_folder_name,
            "Plugin Name": "Error",
            "Plugin Version": "Error",
            "Vendor": str(e)
        }

def scan_plugins():
    result = []
    for plugin in os.listdir(TEAMCITY_PLUGIN_DIR):
        path = os.path.join(TEAMCITY_PLUGIN_DIR, plugin)
        if os.path.isdir(path):
            result.append(parse_teamcity_plugin(path))
    return result

def main():
    print(f"Scanning plugins from: {TEAMCITY_PLUGIN_DIR}")
    data = scan_plugins()
    df = pd.DataFrame(data)
    filename = f"teamcity_plugin_versions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False)
    print(f"Plugin list saved to: {filename}")

if __name__ == "__main__":
    main()
