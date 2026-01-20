from pydantic import BaseModel
from typing import Optional

class WorkerConfig(BaseModel):
    proxy_server_url: str
    target_hostname: str
    reconnect_delay: int
    request_timeout: float
    api_key: Optional[str]

worker_config = WorkerConfig(
    proxy_server_url="ws://localhost:8080/worker",
    target_hostname="http://localhost:11434",
    reconnect_delay=5,      # Delay in seconds before reconnecting
    request_timeout=30.0,   # Request timeout in seconds
    api_key=None            # server api key
)