import psutil
import time
import os
from fastapi import APIRouter, Depends
from .dependencies import get_current_user

router = APIRouter(prefix="/api/system", tags=["System"])

def get_cpu_temp():
    """Försöker hitta CPU-temperatur på olika Linux-system"""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return 0.0
        
        # Prioritera vanliga sensornamn
        for name in ['coretemp', 'cpu_thermal', 'k10temp', 'acpitz']:
            if name in temps:
                # Returnera första kärnans temp
                for entry in temps[name]:
                    if entry.current > 0:
                        return entry.current
        
        # Fallback: ta första bästa som är över 0
        for name, entries in temps.items():
            for entry in entries:
                if entry.current > 0:
                    return entry.current
        return 0.0
    except Exception:
        return 0.0

@router.get("/stats")
async def get_system_stats(user=Depends(get_current_user)):
    # CPU
    cpu_pct = psutil.cpu_percent(interval=0.1) # Kort intervall för responsiveness
    cpu_freq = psutil.cpu_freq()
    current_freq = round(cpu_freq.current, 2) if cpu_freq else 0
    load_avg = os.getloadavg() # [1min, 5min, 15min]

    # RAM
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # DISK (Root)
    disk = psutil.disk_usage('/')
    disk_io = psutil.disk_io_counters()

    # NETWORK (Totala räknare sedan start)
    net = psutil.net_io_counters()

    # UPTIME
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time

    # PROCESSER
    proc_count = len(psutil.pids())

    return {
        "cpu_pct": cpu_pct,
        "cpu_freq": current_freq,
        "load": load_avg,
        "ram_total": mem.total,
        "ram_used": mem.used,
        "ram_percent": mem.percent,
        "swap_percent": swap.percent,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_percent": disk.percent,
        "disk_io_read": disk_io.read_bytes if disk_io else 0,
        "disk_io_write": disk_io.write_bytes if disk_io else 0,
        "net_sent": net.bytes_sent,   # Viktigt för frontend-matten
        "net_recv": net.bytes_recv,   # Viktigt för frontend-matten
        "temp": get_cpu_temp(),
        "uptime": uptime_seconds,
        "process_count": proc_count
    }
