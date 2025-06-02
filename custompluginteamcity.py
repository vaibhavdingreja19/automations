import os

# Set the TeamCity Data Directory path
teamcity_data_dir = "/opt/teamcity/.BuildServer"  # Change this if needed
plugins_dir = os.path.join(teamcity_data_dir, "plugins")

def list_custom_plugins(plugins_path):
    if not os.path.isdir(plugins_path):
        print(f"Plugins directory not found at: {plugins_path}")
        return

    print("Custom Plugins Found:")
    for item in os.listdir(plugins_path):
        full_path = os.path.join(plugins_path, item)
        # TeamCity loads both .zip plugins and directory-based plugins
        if os.path.isdir(full_path) or (os.path.isfile(full_path) and item.endswith(".zip")):
            print(f"- {item}")

if __name__ == "__main__":
    list_custom_plugins(plugins_dir)
