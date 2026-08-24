import os
import sys
import time
import socket
import signal
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("service-manager")

SERVICES_CONFIG = {
    "triage": {
        "name": "Service 1 — Triage Agent",
        "app_module": "services.triage.app.main:app",
        "port": settings.triage_port,
        "url": settings.triage_url,
        "health_endpoint": f"{settings.triage_url}/health",
        "color": "#00f0ff"
    },
    "resolution": {
        "name": "Service 2 — Resolution Agent",
        "app_module": "services.resolution.app.main:app",
        "port": settings.resolution_port,
        "url": settings.resolution_url,
        "health_endpoint": f"{settings.resolution_url}/health",
        "color": "#7928ca"
    },
    "saboteur": {
        "name": "Service 3 — Saboteur Chaos Injector",
        "app_module": "services.saboteur.app.main:app",
        "port": settings.saboteur_port,
        "url": settings.saboteur_url,
        "health_endpoint": f"{settings.saboteur_url}/health",
        "color": "#ff007a"
    }
}

# Global process tracking registry
_processes: Dict[str, subprocess.Popen] = {}


def is_port_in_use(port: int) -> bool:
    """Checks if a TCP port is currently open and bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_health(health_url: str, timeout: float = 1.0) -> bool:
    """Performs HTTP GET check against /health endpoint."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(health_url)
            return resp.status_code == 200
    except Exception:
        return False


class ServiceManager:
    """Manages spawning, lifecycle control, and real-time health probing of swarm microservices."""

    @staticmethod
    def get_service_status(service_key: str) -> Dict[str, Any]:
        cfg = SERVICES_CONFIG.get(service_key)
        if not cfg:
            return {"status": "UNKNOWN", "healthy": False, "pid": None}

        port = cfg["port"]
        health_url = cfg["health_endpoint"]

        # Check HTTP health
        is_healthy = check_health(health_url)
        port_active = is_port_in_use(port)

        proc = _processes.get(service_key)
        pid = proc.pid if (proc and proc.poll() is None) else None

        if is_healthy:
            status_text = "ONLINE"
        elif port_active:
            status_text = "UNHEALTHY / BUSY"
        elif pid is not None:
            status_text = "STARTING"
        else:
            status_text = "OFFLINE"

        return {
            "key": service_key,
            "name": cfg["name"],
            "port": port,
            "url": cfg["url"],
            "status": status_text,
            "healthy": is_healthy,
            "port_active": port_active,
            "pid": pid,
            "color": cfg["color"]
        }

    @staticmethod
    def get_all_statuses() -> Dict[str, Dict[str, Any]]:
        return {key: ServiceManager.get_service_status(key) for key in SERVICES_CONFIG}

    @staticmethod
    def start_service(service_key: str) -> bool:
        cfg = SERVICES_CONFIG.get(service_key)
        if not cfg:
            return False

        current_status = ServiceManager.get_service_status(service_key)
        if current_status["healthy"]:
            logger.info(f"{cfg['name']} is already running and healthy.")
            return True

        # If port is stuck, kill lingering processes on Windows
        if current_status["port_active"]:
            ServiceManager.kill_process_on_port(cfg["port"])
            time.sleep(0.5)

        cmd = [
            sys.executable, "-m", "uvicorn",
            cfg["app_module"],
            "--host", "0.0.0.0",
            "--port", str(cfg["port"]),
            "--log-level", "info"
        ]

        logger.info(f"Starting {cfg['name']} via command: {' '.join(cmd)}")
        try:
            # Create process without creating a blocking window
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=False
            )
            _processes[service_key] = proc

            # Wait up to 3 seconds for health check
            for _ in range(15):
                time.sleep(0.2)
                if check_health(cfg["health_endpoint"], timeout=0.5):
                    logger.info(f"{cfg['name']} started successfully (PID: {proc.pid}).")
                    return True
            return True
        except Exception as e:
            logger.error(f"Failed to start {cfg['name']}: {e}")
            return False

    @staticmethod
    def stop_service(service_key: str) -> bool:
        cfg = SERVICES_CONFIG.get(service_key)
        if not cfg:
            return False

        logger.info(f"Stopping {cfg['name']}...")
        proc = _processes.get(service_key)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            _processes.pop(service_key, None)

        # Force port release if still active
        if is_port_in_use(cfg["port"]):
            ServiceManager.kill_process_on_port(cfg["port"])

        time.sleep(0.5)
        logger.info(f"{cfg['name']} stopped.")
        return True

    @staticmethod
    def restart_service(service_key: str) -> bool:
        ServiceManager.stop_service(service_key)
        time.sleep(0.5)
        return ServiceManager.start_service(service_key)

    @staticmethod
    def start_all_services() -> Dict[str, bool]:
        results = {}
        for key in SERVICES_CONFIG:
            results[key] = ServiceManager.start_service(key)
        return results

    @staticmethod
    def stop_all_services() -> Dict[str, bool]:
        results = {}
        for key in SERVICES_CONFIG:
            results[key] = ServiceManager.stop_service(key)
        return results

    @staticmethod
    def kill_process_on_port(port: int):
        """Cross-platform port clearer (especially effective on Windows)."""
        try:
            if os.name == "nt":
                # Find PID using netstat and kill
                out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
                for line in out.strip().split("\n"):
                    parts = line.strip().split()
                    if len(parts) >= 5 and "LISTENING" in parts:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != os.getpid():
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
