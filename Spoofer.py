import argparse
import ctypes
import json
import logging
import os
import random
import string
import subprocess
import sys
import time
import traceback
import uuid
import winreg
from datetime import datetime
from pathlib import Path

BACKUP_FILE = "hwid_backup.json"


def hwid_is_admin():
    try:
        return os.getuid() == 0
    except AttributeError:
        return ctypes.windll.shell32.IsUserAnAdmin()


def run_as_admin():
    """Restart the script with admin privileges"""
    if hwid_is_admin():
        return True

    print("[*] Requesting Administrator privileges...")

    try:
        # Get the script path and arguments
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        # Use ShellExecute to run as admin
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,  # Parent window
            "runas",  # Verb - requests elevation
            sys.executable,  # Program (python.exe)
            f'"{script}" {params}',  # Parameters
            None,  # Working directory
            1,  # Show window (SW_SHOWNORMAL)
        )

        # ShellExecute returns > 32 if successful
        if ret > 32:
            sys.exit(0)  # Exit this non-elevated instance
        else:
            print(f"[-] Failed to elevate. Error code: {ret}")
            return False

    except Exception as e:
        print(f"[-] Elevation failed: {e}")
        print("[-] Please manually run as Administrator")
        input("Press Enter to exit...")
        return False


def get_current_values():
    """Retrieve all current HWID-related values"""
    values = {}

    # MachineGuid
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        values["MachineGuid"] = winreg.QueryValueEx(key, "MachineGuid")[0]
        winreg.CloseKey(key)
    except:
        values["MachineGuid"] = "ERROR_READING"

    # HwProfileGuid
    try:
        key_path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
        values["HwProfileGuid"] = winreg.QueryValueEx(key, "HwProfileGuid")[0]
        winreg.CloseKey(key)
    except:
        values["HwProfileGuid"] = "ERROR_READING"

    # ProductId
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        values["ProductId"] = winreg.QueryValueEx(key, "ProductId")[0]
        winreg.CloseKey(key)
    except:
        values["ProductId"] = "ERROR_READING"

    # MachineName (Computer Name)
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
            0,
            winreg.KEY_READ,
        )
        values["ComputerName"] = winreg.QueryValueEx(key, "ComputerName")[0]
        winreg.CloseKey(key)
    except:
        values["ComputerName"] = "ERROR_READING"

    # MAC Addresses
    try:
        result = subprocess.run(
            [
                "wmic",
                "nic",
                "where",
                "NetConnectionStatus=2",
                "get",
                "MACAddress,Name",
                "/value",
            ],
            capture_output=True,
            text=True,
        )
        values["MAC_Addresses"] = []
        lines = result.stdout.strip().split("\n")
        current_mac = {}
        for line in lines:
            if "=" in line:
                key_val = line.strip().split("=", 1)
                if len(key_val) == 2:
                    k, v = key_val
                    if k == "MACAddress" and v:
                        current_mac["mac"] = v
                    elif k == "Name":
                        current_mac["name"] = v
                        if "mac" in current_mac:
                            values["MAC_Addresses"].append(current_mac)
                            current_mac = {}
    except:
        values["MAC_Addresses"] = []

    # Disk Serials
    try:
        result = subprocess.run(
            ["wmic", "diskdrive", "get", "Model,SerialNumber", "/value"],
            capture_output=True,
            text=True,
        )
        values["Disk_Serials"] = []
        lines = result.stdout.strip().split("\n\n")
        for block in lines:
            model = ""
            serial = ""
            for line in block.split("\n"):
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k == "Model":
                        model = v
                    elif k == "SerialNumber":
                        serial = v
            if model or serial:
                values["Disk_Serials"].append({"model": model, "serial": serial})
    except:
        values["Disk_Serials"] = []

    values["timestamp"] = datetime.now().isoformat()
    return values


def save_backup(values):
    """Save current values to backup file"""
    try:
        with open(BACKUP_FILE, "w") as f:
            json.dump(values, f, indent=2)
        return True
    except Exception as e:
        print(f"[-] Failed to save backup: {e}")
        return False


def load_backup():
    """Load backup from file"""
    try:
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, "r") as f:
                return json.load(f)
        return None
    except Exception as e:
        print(f"[-] Failed to load backup: {e}")
        return None


def display_current_values(values=None):
    """Display current HWID values"""
    if values is None:
        values = get_current_values()

    print("\n" + "=" * 60)
    print("CURRENT HARDWARE IDENTIFIERS")
    print("=" * 60)
    print(f"MachineGuid:     {values.get('MachineGuid', 'N/A')}")
    print(f"HwProfileGuid:   {values.get('HwProfileGuid', 'N/A')}")
    print(f"ProductId:       {values.get('ProductId', 'N/A')}")
    print(f"ComputerName:    {values.get('ComputerName', 'N/A')}")
    print(f"Timestamp:       {values.get('timestamp', 'N/A')}")

    print("\nNetwork Adapters (MAC Addresses):")
    if macs := values.get("MAC_Addresses", []):
        for adapter in macs:
            print(f"  [{adapter.get('name', 'Unknown')[:40]}]")
            print(f"    MAC: {adapter.get('mac', 'N/A')}")
    else:
        print("  None found or error reading")

    print("\nDisk Drives:")
    if disks := values.get("Disk_Serials", []):
        for disk in disks:
            print(f"  Model:  {disk.get('model', 'Unknown')}")
            print(f"  Serial: {disk.get('serial', 'N/A')}")
    else:
        print("  None found or error reading")

    print("=" * 60 + "\n")


def revert_changes():
    """Restore original values from backup"""
    backup = load_backup()

    if not backup:
        print("[-] No backup file found. Cannot revert.")
        return False

    print("[*] Reverting to backed up values...")
    success = True

    # Restore MachineGuid
    if "MachineGuid" in backup:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            )
            winreg.SetValueEx(
                key, "MachineGuid", 0, winreg.REG_SZ, backup["MachineGuid"]
            )
            winreg.CloseKey(key)
            print(f"[+] Restored MachineGuid: {backup['MachineGuid']}")
        except Exception as e:
            print(f"[-] Failed to restore MachineGuid: {e}")
            success = False

    # Restore HwProfileGuid
    if "HwProfileGuid" in backup:
        try:
            key_path = (
                r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
            )
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(
                key, "HwProfileGuid", 0, winreg.REG_SZ, backup["HwProfileGuid"]
            )
            winreg.CloseKey(key)
            print(f"[+] Restored HwProfileGuid: {backup['HwProfileGuid']}")
        except Exception as e:
            print(f"[-] Failed to restore HwProfileGuid: {e}")
            success = False

    # Restore ProductId
    if "ProductId" in backup:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            )
            winreg.SetValueEx(key, "ProductId", 0, winreg.REG_SZ, backup["ProductId"])
            winreg.CloseKey(key)
            print(f"[+] Restored ProductId: {backup['ProductId']}")
        except Exception as e:
            print(f"[-] Failed to restore ProductId: {e}")
            success = False

    # Restore ComputerName
    if "ComputerName" in backup:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
                0,
                winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(
                key, "ComputerName", 0, winreg.REG_SZ, backup["ComputerName"]
            )
            winreg.CloseKey(key)
            print(f"[+] Restored ComputerName: {backup['ComputerName']}")
        except Exception as e:
            print(f"[-] Failed to restore ComputerName: {e}")
            success = False

    if success:
        print("\n[+] Revert completed successfully!")
        print("[!] System reboot required for changes to take effect.")
    else:
        print("\n[-] Some values failed to revert. Check errors above.")

    return success


def generate_random_guid():
    return str(uuid.uuid4())


def generate_random_product_id():
    chars = string.ascii_uppercase + string.digits
    return "-".join("".join(random.choices(chars, k=5)) for _ in range(4))


def spoof_values():
    """Spoof all registry-based identifiers"""
    print("\n[*] Checking current values and creating backup...")
    current = get_current_values()
    display_current_values(current)

    confirm = input("Create backup and proceed with spoofing? (yes/no): ").lower()
    if confirm != "yes":
        print("[-] Cancelled.")
        return

    if not save_backup(current):
        print("[-] Backup failed. Aborting for safety.")
        return

    print("[*] Applying spoofed values...")

    # Spoof MachineGuid
    try:
        new_guid = generate_random_guid()
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        )
        winreg.SetValueEx(key, "MachineGuid", 0, winreg.REG_SZ, new_guid)
        winreg.CloseKey(key)
        print(f"[+] MachineGuid -> {new_guid}")
    except Exception as e:
        print(f"[-] MachineGuid failed: {e}")

    # Spoof HwProfileGuid
    try:
        new_guid = generate_random_guid()
        key_path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "HwProfileGuid", 0, winreg.REG_SZ, new_guid)
        winreg.CloseKey(key)
        print(f"[+] HwProfileGuid -> {new_guid}")
    except Exception as e:
        print(f"[-] HwProfileGuid failed: {e}")

    # Spoof ProductId
    try:
        new_id = generate_random_product_id()
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        )
        winreg.SetValueEx(key, "ProductId", 0, winreg.REG_SZ, new_id)
        winreg.CloseKey(key)
        print(f"[+] ProductId -> {new_id}")
    except Exception as e:
        print(f"[-] ProductId failed: {e}")

    # Spoof ComputerName
    try:
        new_name = "DESKTOP-" + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=7)
        )
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "ComputerName", 0, winreg.REG_SZ, new_name)
        winreg.CloseKey(key)
        print(f"[+] ComputerName -> {new_name}")
    except Exception as e:
        print(f"[-] ComputerName failed: {e}")

    print("\n[+] Spoofing completed!")
    print("[!] REBOOT REQUIRED for changes to take effect.")
    print(f"[!] Backup saved to: {os.path.abspath(BACKUP_FILE)}")


def show_hwid_menu():
    # Check for admin and auto-elevate if needed
    if not hwid_is_admin():
        run_as_admin()
        # If we get here, elevation failed
        sys.exit(1)

    print("[+] Running with Administrator privileges")

    while True:
        print("\n" + "=" * 40)
        print("HWID TOOL - Registry Identifiers")
        print("=" * 40)
        print("1. Check current HWID values")
        print("2. Spoof HWID")
        print("3. Revert to original values")
        print("4. View backup file contents")
        print("5. Back to main menu")
        print("=" * 40)

        choice = input("Select option (1-5): ").strip()

        if choice == "1":
            current = get_current_values()
            display_current_values(current)
            pause_for_navigation()

        elif choice == "2":
            spoof_values()
            pause_for_navigation()

        elif choice == "3":
            revert_changes()
            pause_for_navigation()

        elif choice == "4":
            backup = load_backup()
            if backup:
                print("\n[*] Backup file contents:")
                display_current_values(backup)
            else:
                print("[-] No backup file found.")
            pause_for_navigation()

        elif choice == "5":
            print("[*] Returning to main menu...")
            break
        else:
            print("[-] Invalid option")


# Unified launcher is at the bottom of this file.


NETWORK_CLASS_GUID = r"{4d36e972-e325-11ce-bfc1-08002be10318}"
NETWORK_CLASS_REG_PATH = (
    r"SYSTEM\CurrentControlSet\Control\Class\\" + NETWORK_CLASS_GUID
)

LOGGER = logging.getLogger("MacAddressTool")


def get_script_folder() -> Path:
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


def get_script_path() -> Path:
    try:
        return Path(__file__).resolve()
    except Exception:
        return Path(sys.argv[0]).resolve()


def get_log_file_path() -> Path:
    return get_script_folder() / "wifi_mac_tool.log"


LOG_FILE = get_log_file_path()


def setup_logging():
    LOGGER.setLevel(logging.DEBUG)

    if LOGGER.handlers:
        return

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except Exception:
        fallback_log = Path.cwd() / "wifi_mac_tool.log"
        file_handler = logging.FileHandler(fallback_log, encoding="utf-8")

    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)

    LOGGER.info("=" * 80)
    LOGGER.info("MAC Address Tool started.")
    LOGGER.info(f"Python version: {sys.version}")
    LOGGER.info(f"Platform: {sys.platform}")
    LOGGER.info(f"Script folder: {get_script_folder()}")
    LOGGER.info(f"Script path: {get_script_path()}")
    LOGGER.info(f"Working directory: {Path.cwd()}")
    LOGGER.info(f"Log file: {LOG_FILE}")


def log_exception(message: str):
    LOGGER.error(message)
    LOGGER.error(traceback.format_exc())


def is_admin() -> bool:
    try:
        admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        LOGGER.debug(f"Admin check result: {admin}")
        return admin
    except Exception:
        log_exception("Failed to check admin status.")
        return False


def relaunch_as_admin():
    if sys.platform != "win32":
        return False

    script_path = str(get_script_path())
    args = [script_path] + sys.argv[1:]
    params = subprocess.list2cmdline(args)

    LOGGER.info("Attempting to relaunch as Administrator.")
    LOGGER.info(f"Executable: {sys.executable}")
    LOGGER.info(f"Parameters: {params}")

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            str(get_script_folder()),
            1,
        )

        if result <= 32:
            LOGGER.error(f"ShellExecuteW failed with code: {result}")
            return False

        LOGGER.info("Relaunch request sent successfully.")
        return True

    except Exception:
        log_exception("Failed to relaunch as Administrator.")
        return False


def ensure_admin_or_relaunch():
    if is_admin():
        return

    print("Administrator permission is required.")
    print("Opening the Windows administrator prompt...")

    relaunched = relaunch_as_admin()

    if relaunched:
        sys.exit(0)

    print()
    print("Failed to open the administrator prompt.")
    print("Right-click the script or Command Prompt and choose 'Run as administrator'.")
    print(f"Log file: {LOG_FILE}")
    sys.exit(1)


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell(command: str, timeout: int = 60) -> str:
    LOGGER.debug("Running PowerShell command:")
    LOGGER.debug(command.strip())

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    LOGGER.debug(f"PowerShell return code: {result.returncode}")

    if result.stdout.strip():
        LOGGER.debug("PowerShell stdout:")
        LOGGER.debug(result.stdout.strip())

    if result.stderr.strip():
        LOGGER.debug("PowerShell stderr:")
        LOGGER.debug(result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "PowerShell command failed."
        )

    return result.stdout.strip()


def get_net_adapters():
    command = """
    Get-NetAdapter -Physical |
    Select-Object Name, InterfaceDescription, Status, MacAddress, InterfaceGuid |
    ConvertTo-Json -Depth 4
    """

    LOGGER.info("Getting physical network adapters.")

    output = run_powershell(command)

    if not output:
        LOGGER.warning("Get-NetAdapter returned no output.")
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        LOGGER.error("Failed to parse Get-NetAdapter JSON output.")
        LOGGER.error(output)
        raise

    if isinstance(data, dict):
        adapters = [data]
    else:
        adapters = data

    LOGGER.info(f"Detected {len(adapters)} physical adapter(s).")

    for adapter in adapters:
        LOGGER.debug(
            "Adapter detected: "
            f"Name={adapter.get('Name')}, "
            f"Description={adapter.get('InterfaceDescription')}, "
            f"Status={adapter.get('Status')}, "
            f"MAC={adapter.get('MacAddress')}, "
            f"GUID={adapter.get('InterfaceGuid')}"
        )

    return adapters


def is_wifi_adapter(adapter: dict) -> bool:
    text = (
        str(adapter.get("Name", ""))
        + " "
        + str(adapter.get("InterfaceDescription", ""))
    ).lower()

    wifi_keywords = [
        "wi-fi",
        "wifi",
        "wireless",
        "wlan",
        "802.11",
    ]

    return any(keyword in text for keyword in wifi_keywords)


def is_ethernet_adapter(adapter: dict) -> bool:
    if is_wifi_adapter(adapter):
        return False

    text = (
        str(adapter.get("Name", ""))
        + " "
        + str(adapter.get("InterfaceDescription", ""))
    ).lower()

    ethernet_keywords = [
        "ethernet",
        "intel(r) ethernet",
        "realtek pcie gbe",
        "realtek gaming",
        "lan",
        "gbe",
        "2.5gbe",
        "i219",
        "i225",
        "i226",
        "killer e",
        "network connection",
    ]

    return any(keyword in text for keyword in ethernet_keywords)


def get_adapter_kind(adapter: dict) -> str:
    if is_wifi_adapter(adapter):
        return "Wi-Fi"

    if is_ethernet_adapter(adapter):
        return "Ethernet"

    return "Other"


def get_target_adapters(adapters):
    targets = []

    for adapter in adapters:
        if is_wifi_adapter(adapter) or is_ethernet_adapter(adapter):
            targets.append(adapter)

    return targets


def generate_random_mac() -> str:
    first_byte = random.randint(0x00, 0xFF)

    first_byte |= 0x02
    first_byte &= 0xFE

    mac_bytes = [first_byte] + [random.randint(0x00, 0xFF) for _ in range(5)]
    mac = "".join(f"{byte:02X}" for byte in mac_bytes)

    LOGGER.info(f"Generated random locally administered MAC: {format_mac(mac)}")

    return mac


def format_mac(mac_12_chars: str) -> str:
    if mac_12_chars is None:
        return "None"

    mac = str(mac_12_chars).replace("-", "").replace(":", "").replace(" ", "").strip()

    if len(mac) != 12:
        return str(mac_12_chars)

    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


def normalize_mac(mac: str) -> str:
    if mac is None:
        return ""

    return str(mac).replace("-", "").replace(":", "").replace(" ", "").upper()


def find_adapter_registry_key(interface_guid: str):
    clean_guid = str(interface_guid).strip("{}").lower()

    LOGGER.info(f"Searching registry for adapter GUID: {clean_guid}")

    try:
        root = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            NETWORK_CLASS_REG_PATH,
            0,
            winreg.KEY_READ,
        )
    except Exception:
        log_exception("Failed to open network adapter registry class path.")
        return None

    try:
        index = 0

        while True:
            try:
                subkey_name = winreg.EnumKey(root, index)
                index += 1

                subkey_path = NETWORK_CLASS_REG_PATH + "\\" + subkey_name

                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        subkey_path,
                        0,
                        winreg.KEY_READ,
                    ) as subkey:
                        try:
                            value, _ = winreg.QueryValueEx(subkey, "NetCfgInstanceId")
                            registry_guid = str(value).strip("{}").lower()

                            LOGGER.debug(
                                f"Checking registry subkey {subkey_name}: "
                                f"NetCfgInstanceId={registry_guid}"
                            )

                            if registry_guid == clean_guid:
                                LOGGER.info(f"Matched registry key: {subkey_path}")
                                return subkey_path

                        except FileNotFoundError:
                            continue

                except PermissionError:
                    LOGGER.warning(f"Permission denied reading subkey: {subkey_path}")
                    continue

            except OSError:
                break

    finally:
        winreg.CloseKey(root)

    LOGGER.warning(f"No registry key matched adapter GUID: {clean_guid}")
    return None


def get_registry_mac_address(registry_path: str):
    LOGGER.info(f"Reading custom MAC from registry path: {registry_path}")

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            registry_path,
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "NetworkAddress")
            LOGGER.info(f"Registry NetworkAddress value: {format_mac(value)}")
            return str(value)

    except FileNotFoundError:
        LOGGER.info("No custom NetworkAddress registry value found.")
        return None

    except Exception:
        log_exception("Failed to read custom NetworkAddress registry value.")
        return None


def set_mac_address(registry_path: str, mac_12_chars: str):
    LOGGER.info(
        f"Writing custom MAC to registry: {format_mac(mac_12_chars)} "
        f"at {registry_path}"
    )

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        registry_path,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "NetworkAddress", 0, winreg.REG_SZ, mac_12_chars)

    LOGGER.info("Registry NetworkAddress value written successfully.")


def remove_custom_mac_address(registry_path: str) -> bool:
    LOGGER.info(f"Removing custom NetworkAddress value from: {registry_path}")

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            registry_path,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, "NetworkAddress")

        LOGGER.info("Custom NetworkAddress registry value removed successfully.")
        return True

    except FileNotFoundError:
        LOGGER.info(
            "No custom NetworkAddress value existed, so there was nothing to remove."
        )
        return True

    except Exception:
        log_exception("Failed to remove custom NetworkAddress registry value.")
        return False


def restart_adapter(adapter_name: str):
    LOGGER.info(f"Restarting adapter: {adapter_name}")

    print(f"Restarting adapter: {adapter_name}")

    run_powershell(f"Disable-NetAdapter -Name {ps_quote(adapter_name)} -Confirm:$false")

    LOGGER.info("Adapter disabled.")
    time.sleep(3)

    run_powershell(f"Enable-NetAdapter -Name {ps_quote(adapter_name)} -Confirm:$false")

    LOGGER.info("Adapter enabled.")
    time.sleep(4)


def get_fresh_adapter_by_guid(interface_guid: str):
    LOGGER.info(f"Refreshing adapter info for GUID: {interface_guid}")

    adapters = get_net_adapters()

    for adapter in adapters:
        if str(adapter.get("InterfaceGuid", "")).lower() == str(interface_guid).lower():
            LOGGER.info("Found refreshed adapter info.")
            return adapter

    LOGGER.warning("Could not find refreshed adapter info.")
    return None


def print_current_target_macs():
    adapters = get_net_adapters()

    if not adapters:
        LOGGER.warning("No network adapters found.")
        print("No network adapters were found.")
        return

    targets = get_target_adapters(adapters)

    if not targets:
        print("No Wi-Fi or Ethernet adapters were found.")
        return

    print()
    print("Current MAC addresses:")
    print()

    for adapter in targets:
        kind = get_adapter_kind(adapter)
        registry_path = find_adapter_registry_key(adapter["InterfaceGuid"])
        custom_mac = None

        if registry_path:
            custom_mac = get_registry_mac_address(registry_path)

        LOGGER.info(
            f"{kind} adapter MAC info: "
            f"Name={adapter.get('Name')}, "
            f"Description={adapter.get('InterfaceDescription')}, "
            f"Status={adapter.get('Status')}, "
            f"ActiveMAC={adapter.get('MacAddress')}, "
            f"CustomRegistryMAC={format_mac(custom_mac) if custom_mac else 'None'}"
        )

        print(f"Type: {kind}")
        print(f"Adapter: {adapter.get('Name')}")
        print(f"Description: {adapter.get('InterfaceDescription')}")
        print(f"Status: {adapter.get('Status')}")
        print(f"Active MAC: {adapter.get('MacAddress')}")

        if custom_mac:
            print(f"Custom registry MAC: {format_mac(custom_mac)}")
        else:
            print("Custom registry MAC: None / default hardware MAC")

        print()


def randomize_single_adapter(adapter: dict) -> bool:
    kind = get_adapter_kind(adapter)
    adapter_name = adapter["Name"]
    interface_guid = adapter["InterfaceGuid"]

    print("=" * 60)
    print(f"Randomizing {kind} adapter: {adapter_name}")
    print("=" * 60)

    LOGGER.info(f"Starting randomization for {kind} adapter: {adapter_name}")

    registry_path = find_adapter_registry_key(interface_guid)

    if registry_path is None:
        LOGGER.error(f"Could not find registry entry for adapter: {adapter_name}")
        print("Could not find the registry entry for this adapter.")
        return False

    old_mac = adapter.get("MacAddress")
    old_custom_mac = get_registry_mac_address(registry_path)
    new_mac = generate_random_mac()

    LOGGER.info(f"Selected adapter: {adapter_name}")
    LOGGER.info(f"Adapter kind: {kind}")
    LOGGER.info(f"Interface GUID: {interface_guid}")
    LOGGER.info(f"Old active MAC: {old_mac}")
    LOGGER.info(
        f"Old custom registry MAC: {format_mac(old_custom_mac) if old_custom_mac else 'None'}"
    )
    LOGGER.info(f"New random MAC: {format_mac(new_mac)}")

    print(f"Old active MAC: {old_mac}")

    if old_custom_mac:
        print(f"Old custom registry MAC: {format_mac(old_custom_mac)}")
    else:
        print("Old custom registry MAC: None / default hardware MAC")

    print(f"New random MAC: {format_mac(new_mac)}")
    print()

    try:
        set_mac_address(registry_path, new_mac)
        restart_adapter(adapter_name)
    except Exception:
        log_exception(f"Failed while randomizing adapter: {adapter_name}")
        print("Failed while changing/restarting this adapter.")
        return False

    print()
    print("Verification:")
    print()

    if fresh_adapter := get_fresh_adapter_by_guid(interface_guid):
        active_mac = fresh_adapter.get("MacAddress")

        LOGGER.info(f"Verification active MAC: {active_mac}")
        LOGGER.info(f"Verification expected MAC: {format_mac(new_mac)}")

        print(f"Current active MAC: {active_mac}")
        print(f"Expected MAC: {format_mac(new_mac)}")

        if normalize_mac(active_mac) == normalize_mac(new_mac):
            LOGGER.info(f"{kind} MAC address changed successfully.")
            print("Result: MAC address changed successfully.")
            print()
            return True

        LOGGER.warning(
            "Registry value changed, but active MAC does not match. "
            "Driver may block custom MAC addresses or Windows may need a restart."
        )

        print(
            "Result: The registry value was changed, but the active MAC does not match."
        )
        print(
            "Your driver may block custom MAC addresses, or Windows may need another restart."
        )
        print()
        return False

    LOGGER.error("Could not re-check the adapter after restarting it.")
    print("Could not re-check the adapter after restarting it.")
    print()
    return False


def randomize_all_supported_adapters():
    LOGGER.info("Starting Wi-Fi/Ethernet MAC randomization.")

    adapters = get_net_adapters()

    if not adapters:
        LOGGER.error("No network adapters were found.")
        print("No network adapters were found.")
        sys.exit(1)

    targets = get_target_adapters(adapters)

    if not targets:
        print("No Wi-Fi or Ethernet adapters were found.")
        return

    print()
    print("This will randomize all detected Wi-Fi and Ethernet adapters.")
    print("Detected target adapters:")
    print()

    for adapter in targets:
        print(
            f"- {get_adapter_kind(adapter)}: {adapter.get('Name')} - "
            f"{adapter.get('InterfaceDescription')} "
            f"[Current MAC: {adapter.get('MacAddress')}]"
        )

    print()

    success_count = 0
    fail_count = 0

    for adapter in targets:
        try:
            if randomize_single_adapter(adapter):
                success_count += 1
            else:
                fail_count += 1
        except Exception:
            fail_count += 1
            log_exception(
                f"Unhandled error while randomizing adapter: {adapter.get('Name')}"
            )
            print(f"Unhandled error while randomizing adapter: {adapter.get('Name')}")

    print("=" * 60)
    print("Randomizations finished.")
    print(f"Successful: {success_count}")
    print(f"Failed or blocked by driver: {fail_count}")
    print(f"Log file: {LOG_FILE}")
    print("=" * 60)
    print()


def revert_single_adapter(adapter: dict) -> bool:
    kind = get_adapter_kind(adapter)
    adapter_name = adapter["Name"]
    interface_guid = adapter["InterfaceGuid"]

    print("=" * 60)
    print(f"Reverting {kind} adapter: {adapter_name}")
    print("=" * 60)

    LOGGER.info(f"Starting revert for {kind} adapter: {adapter_name}")

    registry_path = find_adapter_registry_key(interface_guid)

    if registry_path is None:
        LOGGER.error(f"Could not find registry entry for adapter: {adapter_name}")
        print("Could not find the registry entry for this adapter.")
        return False

    print(f"Current active MAC: {adapter.get('MacAddress')}")

    if old_custom_mac := get_registry_mac_address(registry_path):
        print(f"Custom registry MAC being removed: {format_mac(old_custom_mac)}")
    else:
        print("No custom registry MAC was found.")

    print()

    removed = remove_custom_mac_address(registry_path)

    if not removed:
        LOGGER.error(
            f"Failed to remove custom MAC registry value for adapter: {adapter_name}"
        )
        print("Failed to remove the custom MAC registry value.")
        return False

    try:
        restart_adapter(adapter_name)
    except Exception:
        log_exception(f"Failed while restarting adapter during revert: {adapter_name}")
        print("Failed while restarting this adapter.")
        return False

    print()
    print("Verification:")
    print()

    if fresh_adapter := get_fresh_adapter_by_guid(interface_guid):
        active_mac = fresh_adapter.get("MacAddress")

        LOGGER.info(f"Revert verification active MAC: {active_mac}")

        print(f"Current active MAC after revert: {active_mac}")
        print("Result: Revert completed.")
        print()
        return True

    LOGGER.error("Could not re-check the adapter after reverting.")
    print("Could not re-check the adapter after reverting.")
    print()
    return False


def revert_all_supported_adapters():
    LOGGER.info("Starting Wi-Fi/Ethernet MAC revert.")

    adapters = get_net_adapters()

    if not adapters:
        LOGGER.error("No network adapters were found.")
        print("No network adapters were found.")
        sys.exit(1)

    targets = get_target_adapters(adapters)

    if not targets:
        print("No Wi-Fi or Ethernet adapters were found.")
        return

    print()
    print("This will revert all detected Wi-Fi and Ethernet adapters.")
    print("Detected target adapters:")
    print()

    for adapter in targets:
        print(
            f"- {get_adapter_kind(adapter)}: {adapter.get('Name')} - "
            f"{adapter.get('InterfaceDescription')} "
            f"[Current MAC: {adapter.get('MacAddress')}]"
        )

    print()

    success_count = 0
    fail_count = 0

    for adapter in targets:
        try:
            if revert_single_adapter(adapter):
                success_count += 1
            else:
                fail_count += 1
        except Exception:
            fail_count += 1
            log_exception(
                f"Unhandled error while reverting adapter: {adapter.get('Name')}"
            )
            print(f"Unhandled error while reverting adapter: {adapter.get('Name')}")

    print("=" * 60)
    print("Revert finished.")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Log file: {LOG_FILE}")
    print("=" * 60)
    print()


def open_log_file():
    print(f"Log file: {LOG_FILE}")

    try:
        subprocess.Popen(["notepad.exe", str(LOG_FILE)])
    except Exception:
        log_exception("Failed to open log file in Notepad.")
        print("Could not open the log file automatically.")


def show_mac_menu():
    while True:
        print()
        print("MAC ADDRESS TOOL - Wi-Fi / Ethernet")
        print("1. Check MAC Addresses")
        print("2. Randomize MAC Addresses")
        print("3. Revert MAC Addresses")
        print("4. Show log file path")
        print("5. Open log file")
        print("6. Back to main menu")
        print()

        choice = input("Choose an option: ").strip()

        LOGGER.info(f"Menu choice selected: {choice}")

        if choice == "1":
            print_current_target_macs()
        elif choice == "2":
            randomize_all_supported_adapters()
        elif choice == "3":
            revert_all_supported_adapters()
        elif choice == "4":
            print(f"Log file: {LOG_FILE}")
        elif choice == "5":
            open_log_file()
        elif choice == "6":
            LOGGER.info("User returned to main menu from MAC menu.")
            break
        else:
            print("Invalid option.")
            LOGGER.warning(f"Invalid menu option: {choice}")


def run_mac_cli_or_menu():
    if sys.platform != "win32":
        LOGGER.error("This script was run on a non-Windows platform.")
        print("This script is for Windows only.")
        sys.exit(1)

    ensure_admin_or_relaunch()

    parser = argparse.ArgumentParser(
        description="Check, randomize, or revert Windows Wi-Fi/Ethernet MAC addresses."
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check all detected Wi-Fi and Ethernet MAC addresses.",
    )

    parser.add_argument(
        "--randomize",
        action="store_true",
        help="Randomize all detected Wi-Fi and Ethernet MAC addresses.",
    )

    parser.add_argument(
        "--revert",
        action="store_true",
        help="Revert all detected Wi-Fi and Ethernet adapters to default MAC behavior.",
    )

    parser.add_argument(
        "--log",
        action="store_true",
        help="Show the log file path.",
    )

    parser.add_argument(
        "--open-log",
        action="store_true",
        help="Open the log file in Notepad.",
    )

    args = parser.parse_args()

    LOGGER.info(f"Arguments: {vars(args)}")

    if args.log:
        print(f"Log file: {LOG_FILE}")
    elif args.open_log:
        open_log_file()
    elif args.check:
        print_current_target_macs()
    elif args.randomize:
        randomize_all_supported_adapters()
    elif args.revert:
        revert_all_supported_adapters()
    else:
        show_mac_menu()



def pause_for_navigation():
    input("Press Enter to return to the menu...")


def clear_navigation_screen():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        print("\n" * 3)


def print_navigation_header(title: str):
    print()
    print("=" * 64)
    print(title.center(64))
    print("=" * 64)


def show_status_overview():
    print_navigation_header("CURRENT STATUS OVERVIEW")
    print("HWID / registry values:")
    display_current_values(get_current_values())

    print("Wi-Fi / Ethernet MAC addresses:")
    try:
        print_current_target_macs()
    except Exception as error:
        LOGGER.error("Failed while showing MAC status overview.")
        LOGGER.error(str(error))
        print(f"Could not load MAC address status: {error}")

    pause_for_navigation()


def show_main_menu():
    if sys.platform != "win32":
        print("This script is for Windows only.")
        sys.exit(1)

    ensure_admin_or_relaunch()

    while True:
        clear_navigation_screen()
        print_navigation_header("HWID + MAC TOOL")
        print("1. HWID / registry identifier tools")
        print("2. Wi-Fi / Ethernet MAC tools")
        print("3. Current status overview")
        print("4. Show log file path")
        print("5. Open log file")
        print("6. Exit")
        print("=" * 64)

        choice = input("Choose an option (1-6): ").strip().lower()

        LOGGER.info(f"Main navigation choice selected: {choice}")

        if choice in {"1", "hwid", "h"}:
            show_hwid_menu()
        elif choice in {"2", "mac", "m"}:
            show_mac_menu()
        elif choice in {"3", "status", "s"}:
            show_status_overview()
        elif choice in {"4", "log", "l"}:
            print()
            print(f"Log file: {LOG_FILE}")
            pause_for_navigation()
        elif choice in {"5", "open-log", "open"}:
            open_log_file()
            pause_for_navigation()
        elif choice in {"6", "exit", "quit", "q"}:
            LOGGER.info("User exited from main navigation menu.")
            print("Exiting...")
            break
        else:
            print("Invalid option.")
            pause_for_navigation()


if __name__ == "__main__":
    setup_logging()

    try:
        # Keep existing MAC command-line shortcuts working.
        mac_cli_flags = {"--check", "--randomize", "--revert", "--log", "--open-log"}
        if any(arg in mac_cli_flags for arg in sys.argv[1:]):
            run_mac_cli_or_menu()
        else:
            show_main_menu()

        LOGGER.info("HWID + MAC Tool finished normally.")
    except KeyboardInterrupt:
        LOGGER.warning("User interrupted the script with Ctrl+C.")
        print()
        print("Cancelled.")
        print(f"Log file: {LOG_FILE}")
    except Exception as error:
        LOGGER.critical("Unhandled error occurred.")
        LOGGER.critical(str(error))
        LOGGER.critical(traceback.format_exc())

        print()
        print("An error occurred.")
        print(str(error))
        print()
        print(f"Log file: {LOG_FILE}")
        print("Open the log file and check the newest error at the bottom.")
        sys.exit(1)
