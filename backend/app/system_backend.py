import psutil
import time
import os
from fastapi import APIRouter, Depends
from .dependencies import get_current_user

router = APIRouter(prefix="/api/system", tags=["System"])

def get_cpu_temps_per_core(core_count):
    """
    Försöker mappa temperaturer till kärnor.
    Returnerar en lista med temperaturer [t_core0, t_core1, ...].
    Om exakta kärn-temps saknas, används paket-temp eller 0.
    """
    temps = psutil.sensors_temperatures()
    core_temps = [0.0] * core_count
    
    if not temps:
        return core_temps

    # Prioritera 'coretemp' (Intel) eller 'k10temp' (AMD)
    sensor_data = temps.get('coretemp') or temps.get('k10temp') or temps.get('cpu_thermal')
    
    if sensor_data:
        # Försök hitta specifika Core-entries (t.ex. "Core 0", "Core 1")
        mapped_temps = []
        package_temp = 0.0
        
        for entry in sensor_data:
            if entry.label.startswith('Core'):
                mapped_temps.append(entry.current)
            elif 'Package' in entry.label or 'Tdie' in entry.label:
                package_temp = entry.current
                
        # Om vi hittade specifika kärnor och antalet stämmer (eller är fler/färre pga hyperthreading)
        if mapped_temps:
            # Om vi har färre temp-sensorer än logiska kärnor (vanligt vid hyperthreading)
            # Mappa sensorn till båda logiska trådarna
            if len(mapped_temps) < core_count:
                expanded_temps = []
                ratio = core_count // len(mapped_temps)
                for t in mapped_temps:
                    expanded_temps.extend([t] * ratio)
                # Fyll ut resten om det diffar
                while len(expanded_temps) < core_count:
                    expanded_temps.append(package_temp)
                return expanded_temps[:core_count]
            return mapped_temps[:core_count]
            
        # Fallback: Använd Package temp för alla om inga cores hittades
        if package_temp > 0:
            return [package_temp] * core_count

    # Generell fallback
    return core_temps

@router.get("/stats")
async def get_system_stats(user=Depends(get_current_user)):
    # CPU
    # interval=0.1 gör att anropet tar 100ms, men ger exakt data
    cpu_pct_per_core = psutil.cpu_percent(interval=0.1, percpu=True) 
    cpu_pct_total = sum(cpu_pct_per_core) / len(cpu_pct_per_core)
    
    cpu_freq = psutil.cpu_freq()
    current_freq = round(cpu_freq.current, 2) if cpu_freq else 0
    load_avg = os.getloadavg()

    # TEMPS
    core_temps = get_cpu_temps_per_core(len(cpu_pct_per_core))
    # Huvudtemp (Package eller snitt)
    main_temp = max(core_temps) if core_temps else 0.0

    # RAM
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # DISK (Root)
    disk = psutil.disk_usage('/')
    # Hämtar IO counters. now() behövs för att beräkna hastighet i frontend om backend är stateless, 
    # men här skickar vi bara raw bytes så får frontend räkna delta.
    disk_io = psutil.disk_io_counters()

    # NETWORK
    net = psutil.net_io_counters()

    # UPTIME
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time

    # PROCESSER
    proc_count = len(psutil.pids())

    # Bygg core-objekt lista
    cores_data = []
    for i, load in enumerate(cpu_pct_per_core):
        cores_data.append({
            "id": i,
            "load": load,
            "temp": core_temps[i] if i < len(core_temps) else main_temp
        })

    return {
        "cpu_pct": cpu_pct_total,
        "cpu_cores": cores_data, # NY DATA
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
        "net_sent": net.bytes_sent,
        "net_recv": net.bytes_recv,
        "temp": main_temp,
        "uptime": uptime_seconds,
        "process_count": proc_count
    }