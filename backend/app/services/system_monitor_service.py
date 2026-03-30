"""
Cross-Platform System Monitor Service.

Provides real-time server utilization metrics that work on:
- Linux (Ubuntu, CentOS, Debian, etc.)
- macOS (Intel and Apple Silicon)
- Windows (Server and Desktop)

Uses psutil for cross-platform compatibility.

Note: When running inside Docker:
- CPU metrics reflect the host system
- Memory metrics may reflect container limits if set
- Disk metrics reflect the container's filesystem
"""

import asyncio
import os
import platform
import socket
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import psutil

from app.logs.logger import get_logger

logger = get_logger(__name__)


def is_running_in_docker() -> bool:
    """Detect if we're running inside a Docker container."""
    # Check for .dockerenv file
    if Path("/.dockerenv").exists():
        return True
    
    # Check cgroup (Linux)
    try:
        with open("/proc/1/cgroup", "r") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except Exception:
        pass
    
    # Check for Docker-specific environment variables
    if os.environ.get("DOCKER_CONTAINER") or os.environ.get("container"):
        return True
    
    return False


def get_host_disk_info() -> Optional[Dict[str, Any]]:
    """
    Try to get host disk information when running in Docker.
    This works on Linux when /host is mounted from the host system.
    """
    # Common mount points for host filesystem in Docker
    host_paths = ["/host", "/hostfs", "/rootfs"]
    
    for host_path in host_paths:
        if os.path.exists(host_path):
            try:
                usage = psutil.disk_usage(host_path)
                return {
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "usage_percent": usage.percent,
                    "mount_point": host_path,
                    "is_host": True,
                }
            except Exception:
                pass
    
    return None


@dataclass
class CPUMetrics:
    """CPU utilization metrics."""
    usage_percent: float
    core_count: int
    logical_count: int
    frequency_mhz: Optional[float]
    per_core_usage: List[float]
    load_average_1m: Optional[float]
    load_average_5m: Optional[float]
    load_average_15m: Optional[float]


@dataclass
class MemoryMetrics:
    """Memory utilization metrics."""
    total_gb: float
    available_gb: float
    used_gb: float
    usage_percent: float
    swap_total_gb: float
    swap_used_gb: float
    swap_percent: float


@dataclass
class DiskMetrics:
    """Disk utilization metrics."""
    total_gb: float
    used_gb: float
    free_gb: float
    usage_percent: float
    read_bytes_per_sec: float
    write_bytes_per_sec: float
    partitions: List[Dict]


@dataclass
class NetworkMetrics:
    """Network utilization metrics."""
    bytes_sent_per_sec: float
    bytes_recv_per_sec: float
    packets_sent_per_sec: float
    packets_recv_per_sec: float
    connections_count: int
    interfaces: List[Dict]


@dataclass
class ProcessMetrics:
    """Process-level metrics."""
    total_processes: int
    running_processes: int
    sleeping_processes: int
    top_cpu_processes: List[Dict]
    top_memory_processes: List[Dict]


@dataclass
class SystemInfo:
    """Static system information."""
    hostname: str
    platform: str
    platform_release: str
    platform_version: str
    architecture: str
    processor: str
    python_version: str
    boot_time: datetime
    uptime_seconds: float
    is_containerized: bool = False
    container_type: Optional[str] = None  # "docker", "kubernetes", etc.


@dataclass
class ServerMetrics:
    """Complete server metrics snapshot."""
    timestamp: datetime
    system_info: SystemInfo
    cpu: CPUMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    network: NetworkMetrics
    processes: ProcessMetrics
    health_status: str  # healthy, warning, critical
    health_issues: List[str]
    environment_note: Optional[str] = None  # Note about metrics context


class SystemMonitorService:
    """
    Cross-platform system monitoring service.
    
    Provides comprehensive server utilization metrics that work
    consistently across Linux, macOS, and Windows.
    """
    
    # Thresholds for health status
    CPU_WARNING_THRESHOLD = 70
    CPU_CRITICAL_THRESHOLD = 90
    MEMORY_WARNING_THRESHOLD = 75
    MEMORY_CRITICAL_THRESHOLD = 90
    DISK_WARNING_THRESHOLD = 80
    DISK_CRITICAL_THRESHOLD = 95
    
    def __init__(self):
        self._last_network_io = None
        self._last_disk_io = None
        self._last_io_time = None
    
    def get_system_info(self) -> SystemInfo:
        """Get static system information."""
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = time.time() - psutil.boot_time()
        
        # Get processor info (cross-platform)
        processor = platform.processor()
        if not processor:
            # Fallback for some Linux systems
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                            processor = line.split(":")[1].strip()
                            break
            except Exception:
                processor = "Unknown"
        
        # Detect containerization
        containerized = is_running_in_docker()
        container_type = None
        if containerized:
            # Check if running in Kubernetes
            if os.environ.get("KUBERNETES_SERVICE_HOST"):
                container_type = "kubernetes"
            else:
                container_type = "docker"
        
        return SystemInfo(
            hostname=socket.gethostname(),
            platform=platform.system(),
            platform_release=platform.release(),
            platform_version=platform.version(),
            architecture=platform.machine(),
            processor=processor,
            python_version=platform.python_version(),
            boot_time=boot_time,
            uptime_seconds=uptime,
            is_containerized=containerized,
            container_type=container_type,
        )
    
    def get_cpu_metrics(self) -> CPUMetrics:
        """Get CPU utilization metrics."""
        # Overall CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Per-core usage
        per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        
        # CPU frequency (may not be available on all systems)
        freq = psutil.cpu_freq()
        frequency_mhz = freq.current if freq else None
        
        # Load average (Unix-like systems only)
        load_avg = None
        if hasattr(os, 'getloadavg'):
            try:
                load_avg = os.getloadavg()
            except OSError:
                pass
        
        return CPUMetrics(
            usage_percent=cpu_percent,
            core_count=psutil.cpu_count(logical=False) or 1,
            logical_count=psutil.cpu_count(logical=True) or 1,
            frequency_mhz=frequency_mhz,
            per_core_usage=per_core,
            load_average_1m=load_avg[0] if load_avg else None,
            load_average_5m=load_avg[1] if load_avg else None,
            load_average_15m=load_avg[2] if load_avg else None,
        )
    
    def get_memory_metrics(self) -> MemoryMetrics:
        """Get memory utilization metrics."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return MemoryMetrics(
            total_gb=round(mem.total / (1024 ** 3), 2),
            available_gb=round(mem.available / (1024 ** 3), 2),
            used_gb=round(mem.used / (1024 ** 3), 2),
            usage_percent=mem.percent,
            swap_total_gb=round(swap.total / (1024 ** 3), 2),
            swap_used_gb=round(swap.used / (1024 ** 3), 2),
            swap_percent=swap.percent,
        )
    
    def get_disk_metrics(self, path: str = "/") -> DiskMetrics:
        """Get disk utilization metrics."""
        # Handle Windows drive letters
        if platform.system() == "Windows":
            path = "C:\\"
        
        # Disk usage
        try:
            disk = psutil.disk_usage(path)
            total_gb = round(disk.total / (1024 ** 3), 2)
            used_gb = round(disk.used / (1024 ** 3), 2)
            free_gb = round(disk.free / (1024 ** 3), 2)
            usage_percent = disk.percent
        except Exception as e:
            logger.warning("disk_usage_error", path=path, error=str(e))
            total_gb = used_gb = free_gb = 0
            usage_percent = 0
        
        # Disk I/O rates
        read_rate = write_rate = 0
        current_time = time.time()
        
        try:
            current_io = psutil.disk_io_counters()
            if current_io and self._last_disk_io and self._last_io_time:
                time_delta = current_time - self._last_io_time
                if time_delta > 0:
                    read_rate = (current_io.read_bytes - self._last_disk_io.read_bytes) / time_delta
                    write_rate = (current_io.write_bytes - self._last_disk_io.write_bytes) / time_delta
            
            self._last_disk_io = current_io
        except Exception as e:
            logger.debug("disk_io_error", error=str(e))
        
        # Get partition info
        partitions = []
        try:
            for partition in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    partitions.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total_gb": round(usage.total / (1024 ** 3), 2),
                        "used_gb": round(usage.used / (1024 ** 3), 2),
                        "percent": usage.percent,
                    })
                except (PermissionError, OSError):
                    continue
        except Exception as e:
            logger.debug("partition_info_error", error=str(e))
        
        return DiskMetrics(
            total_gb=total_gb,
            used_gb=used_gb,
            free_gb=free_gb,
            usage_percent=usage_percent,
            read_bytes_per_sec=round(read_rate, 2),
            write_bytes_per_sec=round(write_rate, 2),
            partitions=partitions,
        )
    
    def get_network_metrics(self) -> NetworkMetrics:
        """Get network utilization metrics."""
        current_time = time.time()
        
        # Network I/O rates
        bytes_sent_rate = bytes_recv_rate = 0
        packets_sent_rate = packets_recv_rate = 0
        
        try:
            current_io = psutil.net_io_counters()
            if current_io and self._last_network_io and self._last_io_time:
                time_delta = current_time - self._last_io_time
                if time_delta > 0:
                    bytes_sent_rate = (current_io.bytes_sent - self._last_network_io.bytes_sent) / time_delta
                    bytes_recv_rate = (current_io.bytes_recv - self._last_network_io.bytes_recv) / time_delta
                    packets_sent_rate = (current_io.packets_sent - self._last_network_io.packets_sent) / time_delta
                    packets_recv_rate = (current_io.packets_recv - self._last_network_io.packets_recv) / time_delta
            
            self._last_network_io = current_io
        except Exception as e:
            logger.debug("network_io_error", error=str(e))
        
        # Update last IO time
        self._last_io_time = current_time
        
        # Connection count
        try:
            connections = len(psutil.net_connections(kind='inet'))
        except (psutil.AccessDenied, OSError):
            connections = 0
        
        # Network interfaces
        interfaces = []
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            
            for iface_name, iface_addrs in addrs.items():
                iface_info = {
                    "name": iface_name,
                    "is_up": stats.get(iface_name, {}).isup if iface_name in stats else False,
                    "addresses": [],
                }
                
                for addr in iface_addrs:
                    if addr.family.name == "AF_INET":
                        iface_info["addresses"].append({
                            "type": "IPv4",
                            "address": addr.address,
                        })
                    elif addr.family.name == "AF_INET6":
                        iface_info["addresses"].append({
                            "type": "IPv6",
                            "address": addr.address,
                        })
                
                if iface_info["addresses"]:
                    interfaces.append(iface_info)
        except Exception as e:
            logger.debug("network_interfaces_error", error=str(e))
        
        return NetworkMetrics(
            bytes_sent_per_sec=round(bytes_sent_rate, 2),
            bytes_recv_per_sec=round(bytes_recv_rate, 2),
            packets_sent_per_sec=round(packets_sent_rate, 2),
            packets_recv_per_sec=round(packets_recv_rate, 2),
            connections_count=connections,
            interfaces=interfaces,
        )
    
    def get_process_metrics(self, top_n: int = 5) -> ProcessMetrics:
        """Get process-level metrics."""
        total = running = sleeping = 0
        processes_info = []
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    info = proc.info
                    total += 1
                    
                    status = info.get('status', '')
                    if status == psutil.STATUS_RUNNING:
                        running += 1
                    elif status == psutil.STATUS_SLEEPING:
                        sleeping += 1
                    
                    processes_info.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'cpu_percent': info['cpu_percent'] or 0,
                        'memory_percent': info['memory_percent'] or 0,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.debug("process_metrics_error", error=str(e))
        
        # Sort by CPU and memory usage
        top_cpu = sorted(processes_info, key=lambda x: x['cpu_percent'], reverse=True)[:top_n]
        top_memory = sorted(processes_info, key=lambda x: x['memory_percent'], reverse=True)[:top_n]
        
        return ProcessMetrics(
            total_processes=total,
            running_processes=running,
            sleeping_processes=sleeping,
            top_cpu_processes=top_cpu,
            top_memory_processes=top_memory,
        )
    
    def get_health_status(
        self,
        cpu: CPUMetrics,
        memory: MemoryMetrics,
        disk: DiskMetrics,
    ) -> tuple[str, List[str]]:
        """
        Determine overall health status based on metrics.
        
        Returns:
            Tuple of (status, list of issues)
        """
        issues = []
        status = "healthy"
        
        # Check CPU
        if cpu.usage_percent >= self.CPU_CRITICAL_THRESHOLD:
            issues.append(f"CPU usage critical: {cpu.usage_percent:.1f}%")
            status = "critical"
        elif cpu.usage_percent >= self.CPU_WARNING_THRESHOLD:
            issues.append(f"CPU usage high: {cpu.usage_percent:.1f}%")
            if status != "critical":
                status = "warning"
        
        # Check Memory
        if memory.usage_percent >= self.MEMORY_CRITICAL_THRESHOLD:
            issues.append(f"Memory usage critical: {memory.usage_percent:.1f}%")
            status = "critical"
        elif memory.usage_percent >= self.MEMORY_WARNING_THRESHOLD:
            issues.append(f"Memory usage high: {memory.usage_percent:.1f}%")
            if status != "critical":
                status = "warning"
        
        # Check Disk
        if disk.usage_percent >= self.DISK_CRITICAL_THRESHOLD:
            issues.append(f"Disk usage critical: {disk.usage_percent:.1f}%")
            status = "critical"
        elif disk.usage_percent >= self.DISK_WARNING_THRESHOLD:
            issues.append(f"Disk usage high: {disk.usage_percent:.1f}%")
            if status != "critical":
                status = "warning"
        
        # Check swap usage
        if memory.swap_percent >= 80:
            issues.append(f"Swap usage high: {memory.swap_percent:.1f}%")
            if status != "critical":
                status = "warning"
        
        return status, issues
    
    def get_all_metrics(self) -> ServerMetrics:
        """Get complete server metrics snapshot."""
        system_info = self.get_system_info()
        cpu = self.get_cpu_metrics()
        memory = self.get_memory_metrics()
        disk = self.get_disk_metrics()
        network = self.get_network_metrics()
        processes = self.get_process_metrics()
        
        health_status, health_issues = self.get_health_status(cpu, memory, disk)
        
        # Add environment context note
        environment_note = None
        if system_info.is_containerized:
            environment_note = (
                f"Running in {system_info.container_type or 'container'}. "
                "CPU metrics reflect host system. Memory/Disk may reflect container limits. "
                "For accurate host metrics, deploy monitoring agent directly on the server."
            )
        
        return ServerMetrics(
            timestamp=datetime.utcnow(),
            system_info=system_info,
            cpu=cpu,
            memory=memory,
            disk=disk,
            network=network,
            processes=processes,
            health_status=health_status,
            health_issues=health_issues,
            environment_note=environment_note,
        )
    
    def to_dict(self, metrics: ServerMetrics) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "timestamp": metrics.timestamp.isoformat(),
            "system_info": {
                **asdict(metrics.system_info),
                "boot_time": metrics.system_info.boot_time.isoformat(),
                "uptime_formatted": self._format_uptime(metrics.system_info.uptime_seconds),
            },
            "cpu": asdict(metrics.cpu),
            "memory": asdict(metrics.memory),
            "disk": asdict(metrics.disk),
            "network": asdict(metrics.network),
            "processes": asdict(metrics.processes),
            "health_status": metrics.health_status,
            "health_issues": metrics.health_issues,
            "environment_note": metrics.environment_note,
        }
    
    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime in human-readable format."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "< 1m"


# Singleton instance for reuse
_monitor_instance: Optional[SystemMonitorService] = None


def get_system_monitor() -> SystemMonitorService:
    """Get or create system monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitorService()
    return _monitor_instance


async def get_server_metrics() -> Dict[str, Any]:
    """
    Async wrapper to get server metrics.
    
    Runs CPU-intensive operations in thread pool to avoid blocking.
    """
    monitor = get_system_monitor()
    
    # Run in thread pool since psutil operations can be blocking
    loop = asyncio.get_event_loop()
    metrics = await loop.run_in_executor(None, monitor.get_all_metrics)
    
    return monitor.to_dict(metrics)
