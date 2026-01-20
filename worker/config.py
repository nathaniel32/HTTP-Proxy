from pydantic import BaseModel, Field
from typing import Optional

class WorkerConfig(BaseModel):
    proxy_server_url: str = Field(default="ws://localhost:8080/worker")
    target_hostname: str = Field(default="http://localhost:11434")
    reconnect_delay: int = Field(default=5, description="Delay in seconds before reconnecting")
    request_timeout: float = Field(default=30.0, description="Request timeout in seconds")
    api_key: Optional[str] = Field(default=None, description="API key for authentication (optional)")

worker_config = WorkerConfig(
    api_key = None        # server api key
)