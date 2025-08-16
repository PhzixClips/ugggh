"""
Task Manager for handling background processes and UI updates.
"""

import threading
import queue
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future
from typing import Callable, Any, Dict, Optional, Union

class Task:
    """Represents a unit of work to be executed in the background."""
    def __init__(self, target: Callable, args: tuple = (), kwargs: dict = None,
                 task_type: str = 'thread', on_progress: Optional[Callable] = None,
                 on_complete: Optional[Callable] = None, on_error: Optional[Callable] = None):
        self.task_id = str(uuid.uuid4())
        self.target = target
        self.args = args
        self.kwargs = kwargs if kwargs is not None else {}
        self.task_type = task_type  # 'thread' or 'process'
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.future: Optional[Future] = None
        self.cancelled = False

    def cancel(self):
        """Mark the task as cancelled."""
        self.cancelled = True
        if self.future:
            self.future.cancel()

class TaskManager:
    """Manages background tasks using thread and process pools."""
    def __init__(self, root, max_threads=4, max_processes=2):
        self.root = root
        self.tasks: Dict[str, Task] = {}
        self.ui_queue = queue.Queue()

        self.thread_executor = ThreadPoolExecutor(max_workers=max_threads)
        self.process_executor = ProcessPoolExecutor(max_workers=max_processes)

        self._poll_queue()

    def submit_task(self, task: Task):
        """Submit a task to the appropriate executor."""
        if task.task_id in self.tasks:
            raise ValueError(f"Task with ID {task.task_id} already exists.")

        self.tasks[task.task_id] = task

        executor = self.thread_executor if task.task_type == 'thread' else self.process_executor

        # Wrapper to handle communication back to the main thread
        def task_wrapper():
            try:
                result = task.target(*task.args, **task.kwargs)
                if not task.cancelled:
                    self.ui_queue.put(('complete', task.task_id, result))
            except Exception as e:
                if not task.cancelled:
                    self.ui_queue.put(('error', task.task_id, e))

        task.future = executor.submit(task_wrapper)
        return task.task_id

    def cancel_task(self, task_id: str):
        """Cancel a running task."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.cancel()
            # Further cancellation logic may be needed depending on the task

    def _poll_queue(self):
        """Poll the UI queue for updates from background tasks."""
        try:
            while not self.ui_queue.empty():
                message_type, task_id, data = self.ui_queue.get_nowait()

                task = self.tasks.get(task_id)
                if not task:
                    continue

                if message_type == 'complete':
                    if task.on_complete:
                        task.on_complete(data)
                    del self.tasks[task_id]
                elif message_type == 'error':
                    if task.on_error:
                        task.on_error(data)
                    del self.tasks[task_id]
                elif message_type == 'progress':
                    if task.on_progress:
                        task.on_progress(data)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_queue)

    def shutdown(self):
        """Shutdown the executors."""
        self.thread_executor.shutdown(wait=False)
        self.process_executor.shutdown(wait=False)
