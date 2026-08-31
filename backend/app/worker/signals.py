from celery.signals import task_prerun, task_postrun, task_failure, before_task_publish
from app.core.logging import logger, request_id_var, correlation_id_var
import time

# Dictionary to store task start times
task_start_times = {}

@before_task_publish.connect
def on_before_task_publish(sender=None, headers=None, body=None, **kwargs):
    if headers is not None:
        # Inject correlation ID and request ID into the Celery task headers
        req_id = request_id_var.get()
        corr_id = correlation_id_var.get()
        
        if req_id:
            headers['x_request_id'] = req_id
        if corr_id:
            headers['x_correlation_id'] = corr_id

@task_prerun.connect
def on_task_prerun(task_id, task, *args, **kwargs):
    # Extract headers from the current request
    req = task.request
    
    # Safely get headers
    headers = getattr(req, 'headers', None)
    
    # Celery sometimes puts headers directly on the request for older protocol versions
    # or inside the headers dict for newer protocols. We check both.
    req_id = None
    corr_id = None
    
    if isinstance(headers, dict):
        req_id = headers.get('x_request_id')
        corr_id = headers.get('x_correlation_id')
        
    if not req_id and hasattr(req, 'x_request_id'):
        req_id = getattr(req, 'x_request_id')
        
    if not corr_id and hasattr(req, 'x_correlation_id'):
        corr_id = getattr(req, 'x_correlation_id')
        
    # Re-hydrate the context variables inside the worker process
    if req_id:
        request_id_var.set(req_id)
    if corr_id:
        correlation_id_var.set(corr_id)

    task_start_times[task_id] = time.time()
    
    logger.info(
        f"Celery task started: {task.name}",
        extra={"extra_context": {
            "celery_task_id": task_id,
            "celery_task_name": task.name,
            "event": "celery_task_started"
        }}
    )

@task_postrun.connect
def on_task_postrun(task_id, task, *args, retval=None, state=None, **kwargs):
    start_time = task_start_times.pop(task_id, time.time())
    duration_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        f"Celery task completed: {task.name} with state {state}",
        extra={"extra_context": {
            "celery_task_id": task_id,
            "celery_task_name": task.name,
            "celery_task_state": state,
            "duration_ms": duration_ms,
            "event": "celery_task_completed"
        }}
    )

@task_failure.connect
def on_task_failure(task_id, exception, args, traceback, einfo, **kwargs):
    start_time = task_start_times.pop(task_id, time.time())
    duration_ms = int((time.time() - start_time) * 1000)
    
    # We use sender context to get task name if available
    task_name = kwargs.get('sender', 'unknown').name if hasattr(kwargs.get('sender'), 'name') else 'unknown'
    
    logger.error(
        f"Celery task failed: {task_name} with exception {exception.__class__.__name__}",
        exc_info=exception,
        extra={"extra_context": {
            "celery_task_id": task_id,
            "celery_task_name": task_name,
            "celery_task_state": "FAILURE",
            "duration_ms": duration_ms,
            "exception_class": exception.__class__.__name__,
            "event": "celery_task_failed"
        }}
    )
