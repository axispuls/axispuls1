import os
import json
import hashlib
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from .config_manager import get_base_dir
from .security_utils import atomic_write_json

HARDWARE_CACHE_FILE = get_base_dir() / ".hardware_fingerprint.json"

def _run_powershell_json(cmd: str) -> Any:
    """Executes a PowerShell command that outputs JSON and parses it."""
    try:
        full_cmd = f"powershell -NoProfile -ExecutionPolicy Bypass -Command \"{cmd}\""
        res = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=8
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return None

def collect_hardware_fingerprint() -> Dict[str, Any]:
    """
    Collects full, unforgeable hardware specifications of the system.
    Key components that remain IDENTICAL across Windows reinstallation & disk formatting:
      1. Motherboard Serial Number (BaseBoard)
      2. Processor ID (CPU)
      3. Physical Disk Drive Serial Numbers (SSD / HDD)
      4. BIOS System UUID
      5. Physical Network MAC Address
    """
    hw: Dict[str, Any] = {
        "computer_name": os.environ.get("COMPUTERNAME", platform.node()),
        "user_name": os.environ.get("USERNAME", ""),
        "os_version": f"{platform.system()} {platform.release()} ({platform.version()})",
        "motherboard_serial": "Unknown",
        "motherboard_model": "Unknown",
        "cpu_name": platform.processor() or "Unknown",
        "cpu_id": "Unknown",
        "cpu_cores": os.cpu_count() or 1,
        "disks": [],
        "primary_disk_serial": "Unknown",
        "system_uuid": "Unknown",
        "mac_addresses": [],
        "primary_mac": "Unknown",
        "persistent_hw_hash": "Unknown"
    }

    # 1. Motherboard (Win32_BaseBoard)
    mb_data = _run_powershell_json(
        "Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product, SerialNumber | ConvertTo-Json"
    )
    if isinstance(mb_data, dict):
        hw["motherboard_serial"] = str(mb_data.get("SerialNumber") or "Unknown").strip()
        man = str(mb_data.get("Manufacturer") or "").strip()
        prod = str(mb_data.get("Product") or "").strip()
        hw["motherboard_model"] = f"{man} {prod}".strip() or "Unknown"

    # 2. CPU (Win32_Processor)
    cpu_data = _run_powershell_json(
        "Get-CimInstance Win32_Processor | Select-Object Name, ProcessorId, NumberOfCores | ConvertTo-Json"
    )
    if isinstance(cpu_data, list) and cpu_data:
        cpu_data = cpu_data[0]
    if isinstance(cpu_data, dict):
        hw["cpu_name"] = str(cpu_data.get("Name") or hw["cpu_name"]).strip()
        hw["cpu_id"] = str(cpu_data.get("ProcessorId") or "Unknown").strip()
        if cpu_data.get("NumberOfCores"):
            hw["cpu_cores"] = cpu_data.get("NumberOfCores")

    # 3. Disks (Win32_DiskDrive) - Crucial physical disk serials
    disks_data = _run_powershell_json(
        "Get-CimInstance Win32_DiskDrive | Select-Object Model, SerialNumber, Size | ConvertTo-Json"
    )
    if isinstance(disks_data, dict):
        disks_data = [disks_data]
    elif not isinstance(disks_data, list):
        disks_data = []

    clean_disks = []
    primary_serial = ""
    for d in disks_data:
        if isinstance(d, dict):
            model = str(d.get("Model") or "").strip()
            serial = str(d.get("SerialNumber") or "").strip()
            size = d.get("Size", 0)
            try:
                size_gb = round(float(size) / (1024 ** 3), 1)
            except Exception:
                size_gb = 0
            if serial and serial.lower() != "none":
                clean_disks.append({
                    "model": model,
                    "serial": serial,
                    "size_gb": size_gb
                })
                if not primary_serial:
                    primary_serial = serial

    hw["disks"] = clean_disks
    hw["primary_disk_serial"] = primary_serial or "Unknown"

    # 4. System UUID (Win32_ComputerSystemProduct)
    sys_data = _run_powershell_json(
        "Get-CimInstance Win32_ComputerSystemProduct | Select-Object UUID | ConvertTo-Json"
    )
    if isinstance(sys_data, dict):
        hw["system_uuid"] = str(sys_data.get("UUID") or "Unknown").strip()

    # 5. Network MAC (Win32_NetworkAdapterConfiguration)
    net_data = _run_powershell_json(
        "Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object IPEnabled -eq $true | Select-Object Description, MACAddress | ConvertTo-Json"
    )
    if isinstance(net_data, dict):
        net_data = [net_data]
    elif not isinstance(net_data, list):
        net_data = []

    clean_macs = []
    for n in net_data:
        if isinstance(n, dict):
            mac = str(n.get("MACAddress") or "").strip()
            desc = str(n.get("Description") or "").strip()
            if mac and mac.lower() != "none":
                clean_macs.append(f"{mac} ({desc})")
                if hw["primary_mac"] == "Unknown":
                    hw["primary_mac"] = mac

    hw["mac_addresses"] = clean_macs

    # 6. Fallback if PowerShell returned incomplete info
    if hw["system_uuid"] == "Unknown" or hw["primary_disk_serial"] == "Unknown":
        import uuid
        hw["primary_mac"] = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 48, 8)][::-1])

    # 7. Compute Unforgeable Persistent Hardware Hash (Survives 100% OS Reinstalls)
    # Built from components that NEVER change upon Windows formatting:
    raw_fingerprint = (
        f"{hw['system_uuid']}:"
        f"{hw['motherboard_serial']}:"
        f"{hw['cpu_id']}:"
        f"{hw['primary_disk_serial']}:"
        f"{hw['primary_mac']}"
    )
    sha = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()
    hw["persistent_hw_hash"] = f"AXIS-{sha[:16].upper()}"

    # Cache locally
    try:
        atomic_write_json(HARDWARE_CACHE_FILE, json.dumps(hw, ensure_ascii=False, indent=2))
    except Exception:
        pass

    return hw

def format_hardware_report(hw: Dict[str, Any]) -> str:
    """Formats hardware specifications into an elegant Persian report for Bale."""
    disks_str = ""
    for idx, d in enumerate(hw.get("disks", []), 1):
        disks_str += f"  {idx}. {d.get('model', 'Drive')} ({d.get('size_gb', 0)} GB)\n     سریال: `{d.get('serial', 'Unknown')}`\n"
    if not disks_str:
        disks_str = f"  • سریال اصلی هارد: `{hw.get('primary_disk_serial', 'Unknown')}`\n"

    mac_str = "\n".join([f"  • {m}" for m in hw.get("mac_addresses", [])])
    if not mac_str:
        mac_str = f"  • `{hw.get('primary_mac', 'Unknown')}`"

    report = (
        f"🖥️ برگه جامع مشخصات سخت‌افزاری سیستم (تأیید اصالت دستگاه):\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💻 نام سیستم: {hw.get('computer_name', 'Unknown')}\n"
        f"👤 کاربر ویندوز: {hw.get('user_name', 'Unknown')}\n"
        f"🪟 نسخه سیستم‌عامل: {hw.get('os_version', 'Unknown')}\n\n"
        f"⚙️ مشخصات قطعات سخت‌افزاری ثابت:\n"
        f"• مدل مادربرد: {hw.get('motherboard_model', 'Unknown')}\n"
        f"• شماره سریال مادربرد: `{hw.get('motherboard_serial', 'Unknown')}`\n"
        f"• پردازنده (CPU): {hw.get('cpu_name', 'Unknown')}\n"
        f"• شناسه پردازنده (Processor ID): `{hw.get('cpu_id', 'Unknown')}`\n"
        f"• شناسه سیستمی بایوس (System UUID):\n  `{hw.get('system_uuid', 'Unknown')}`\n\n"
        f"💾 دیسک‌ها و SSDهای فیزیکی (سریال غیرقابل تغییر):\n"
        f"{disks_str}\n"
        f"🌐 آدرس مک کارت شبکه (MAC):\n"
        f"{mac_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔒 شناسه هش سخت‌افزاری ماندگار (Anti-Reinstall ID):\n"
        f"`{hw.get('persistent_hw_hash', 'Unknown')}`\n\n"
        f"📌 نکته فنی برای مدیر:\n"
        f"شناسه هش ماندگار و شماره سریال هاردها حتی پس از تعویض کامل ویندوز و فرمت درایوها کاملاً ثابت می‌مانند. با تطبیق این مقادیر می‌توانید ادعای تعویض ویندوز مشتری را به طور قطعی بررسی فرمایید."
    )
    return report
