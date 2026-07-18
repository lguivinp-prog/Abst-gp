import os
from redis import Redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_conn = Redis.from_url(REDIS_URL)
is_testing = os.getenv("TESTING", "0") == "1"
task_queue = Queue('default', connection=redis_conn, is_async=not is_testing)
ocr_queue = Queue('ocr_tasks', connection=redis_conn, is_async=not is_testing)
