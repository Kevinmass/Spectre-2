"""
Gestor de cola de tareas para procesamiento de documentos.

Este módulo implementa una cola de tareas que permite procesar documentos
de forma asíncrona y controlar el uso de recursos.
"""

import os
import time
import logging
import threading
import queue
import psutil
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from ...config.settings import get_config
from ...indexing.document_registry import get_document_registry

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Estados de una tarea."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    """Prioridades de las tareas."""
    LOW = 1
    MEDIUM = 5
    HIGH = 10

@dataclass
class Task:
    """Representa una tarea en la cola."""
    task_id: str
    task_type: str  # process_document, index_document, etc.
    payload: Dict[str, Any]
    priority: TaskPriority
    created_at: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

class TaskQueue:
    """Cola de tareas para procesamiento asíncrono."""
    
    def __init__(self, max_workers: Optional[int] = None):
        """
        Inicializa la cola de tareas.
        
        Args:
            max_workers: Número máximo de workers (opcional).
        """
        self.config = get_config()
        self.max_workers = max_workers or self.config.system.max_workers
        self.queue = queue.PriorityQueue()
        self.tasks: Dict[str, Task] = {}
        self.workers: List[threading.Thread] = []
        self.worker_locks: Dict[int, threading.Lock] = {}
        self.is_running = False
        self._lock = threading.Lock()
        
        # Métricas
        self.metrics = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "running_tasks": 0
        }
    
    def start(self):
        """Inicia la cola de tareas y los workers."""
        if self.is_running:
            logger.warning("La cola de tareas ya está en ejecución")
            return
        
        self.is_running = True
        
        # Iniciar workers
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(i,),
                name=f"Worker-{i}"
            )
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
            self.worker_locks[i] = threading.Lock()
        
        logger.info(f"Cola de tareas iniciada con {self.max_workers} workers")
    
    def stop(self):
        """Detiene la cola de tareas y los workers."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Detener workers
        for worker in self.workers:
            worker.join(timeout=5)
        
        self.workers = []
        logger.info("Cola de tareas detenida")
    
    def add_task(self, task_type: str, payload: Dict[str, Any], 
                priority: TaskPriority = TaskPriority.MEDIUM) -> str:
        """
        Agrega una nueva tarea a la cola.
        
        Args:
            task_type: Tipo de tarea.
            payload: Datos de la tarea.
            priority: Prioridad de la tarea.
            
        Returns:
            ID de la tarea.
        """
        with self._lock:
            task_id = self._generate_task_id(task_type, payload)
            
            task = Task(
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                priority=priority,
                created_at=datetime.now().isoformat()
            )
            
            self.tasks[task_id] = task
            self.queue.put((-priority.value, time.time(), task_id))
            self.metrics["total_tasks"] += 1
            
            logger.info(f"Tarea agregada: {task_id} ({task_type})")
            return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Obtiene una tarea por su ID."""
        with self._lock:
            return self.tasks.get(task_id)
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Obtiene tareas por estado."""
        with self._lock:
            return [task for task in self.tasks.values() if task.status == status]
    
    def get_pending_tasks(self) -> List[Task]:
        """Obtiene tareas pendientes."""
        return self.get_tasks_by_status(TaskStatus.PENDING)
    
    def get_running_tasks(self) -> List[Task]:
        """Obtiene tareas en ejecución."""
        return self.get_tasks_by_status(TaskStatus.RUNNING)
    
    def get_completed_tasks(self) -> List[Task]:
        """Obtiene tareas completadas."""
        return self.get_tasks_by_status(TaskStatus.COMPLETED)
    
    def get_failed_tasks(self) -> List[Task]:
        """Obtiene tareas fallidas."""
        return self.get_tasks_by_status(TaskStatus.FAILED)
    
    def cancel_task(self, task_id: str):
        """Cancela una tarea."""
        with self._lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    task.status = TaskStatus.CANCELLED
                    self.metrics["cancelled_tasks"] += 1
                    logger.info(f"Tarea cancelada: {task_id}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de la cola de tareas."""
        with self._lock:
            return {
                **self.metrics,
                "queue_size": self.queue.qsize(),
                "workers_count": len(self.workers),
                "running_tasks": len(self.get_running_tasks()),
                "pending_tasks": len(self.get_pending_tasks()),
                "failed_tasks": len(self.get_failed_tasks()),
                "completed_tasks": len(self.get_completed_tasks())
            }
    
    def _worker_loop(self, worker_id: int):
        """Bucle principal de un worker."""
        logger.info(f"Worker-{worker_id} iniciado")
        
        while self.is_running:
            try:
                # Verificar recursos antes de tomar una tarea
                if not self._check_resources():
                    time.sleep(1)
                    continue
                
                # Obtener tarea de la cola
                try:
                    priority, timestamp, task_id = self.queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Procesar tarea
                self._process_task(worker_id, task_id)
                
            except Exception as e:
                logger.error(f"Error en worker-{worker_id}: {e}")
                time.sleep(1)
        
        logger.info(f"Worker-{worker_id} detenido")
    
    def _check_resources(self) -> bool:
        """Verifica si hay recursos disponibles para procesar."""
        try:
            # Verificar uso de CPU
            cpu_usage = psutil.cpu_percent(interval=0.1)
            if cpu_usage > (self.config.system.cpu_usage_limit * 100):
                return False
            
            # Verificar memoria disponible
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            if available_gb < self.config.system.memory_limit_gb:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error verificando recursos: {e}")
            return False
    
    def _process_task(self, worker_id: int, task_id: str):
        """Procesa una tarea específica."""
        with self._lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            if task.status != TaskStatus.PENDING:
                return
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            self.metrics["running_tasks"] += 1
        
        try:
            # Ejecutar la tarea
            self._execute_task(task)
            
            # Marcar como completada
            with self._lock:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                self.metrics["completed_tasks"] += 1
                self.metrics["running_tasks"] -= 1
            
            logger.info(f"Tarea completada: {task_id}")
            
        except Exception as e:
            # Manejar error
            with self._lock:
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    task.status = TaskStatus.FAILED
                    task.error_message = str(e)
                    self.metrics["failed_tasks"] += 1
                    self.metrics["running_tasks"] -= 1
                    logger.error(f"Tarea fallida después de {task.retry_count} intentos: {task_id} - {e}")
                else:
                    task.status = TaskStatus.PENDING
                    self.queue.put((-task.priority.value, time.time(), task_id))
                    logger.warning(f"Tarea reprogramada: {task_id} (intento {task.retry_count})")
    
    def _execute_task(self, task: Task):
        """Ejecuta el procesamiento de una tarea."""
        if task.task_type == "process_document":
            self._process_document_task(task)
        elif task.task_type == "index_document":
            self._index_document_task(task)
        else:
            raise ValueError(f"Tipo de tarea desconocido: {task.task_type}")
    
    def _process_document_task(self, task: Task):
        """Procesa una tarea de documento."""
        file_path = task.payload.get("file_path")
        if not file_path:
            raise ValueError("Ruta de archivo no especificada")
        
        # Aquí iría la lógica de procesamiento de documentos
        # Por ahora, simulamos el procesamiento
        logger.info(f"Procesando documento: {file_path}")
        time.sleep(2)  # Simulación de procesamiento
        
        # Actualizar registro de documentos
        registry = get_document_registry()
        document_id = registry.add_document(file_path)
        registry.update_status(
            document_id,
            "completed",
            processed_at=datetime.now().isoformat(),
            chunks_count=10,  # Simulación
            metadata={"processing_time": 2}
        )
    
    def _index_document_task(self, task: Task):
        """Indexa una tarea de documento."""
        document_id = task.payload.get("document_id")
        if not document_id:
            raise ValueError("ID de documento no especificado")
        
        # Aquí iría la lógica de indexación
        logger.info(f"Indexando documento: {document_id}")
        time.sleep(1)  # Simulación de indexación
    
    def _generate_task_id(self, task_type: str, payload: Dict[str, Any]) -> str:
        """Genera un ID único para la tarea."""
        import hashlib
        combined = f"{task_type}_{str(payload)}_{time.time()}"
        return hashlib.md5(combined.encode()).hexdigest()

# Instancia global de la cola de tareas
_task_queue: Optional[TaskQueue] = None

def get_task_queue() -> TaskQueue:
    """
    Obtiene la instancia global de la cola de tareas.
    
    Returns:
        Instancia de TaskQueue.
    """
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue

def set_task_queue(queue: TaskQueue):
    """
    Establece la instancia global de la cola de tareas.
    
    Args:
        queue: Instancia de TaskQueue.
    """
    global _task_queue
    _task_queue = queue