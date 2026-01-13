## Deploy Server

```
docker build -t nathaniels32/ollama-proxy-python:latest .
```

```
docker push nathaniels32/ollama-proxy-python:latest
```

```
cloudron install --image nathaniels32/ollama-proxy-python:latest
```

```
ollama-proxy-python.3d-medico.com
```

## Run Worker in IOS

- **Make Env**
    ```
    python3 -m venv worker_env
    ```

- **Activate the Env**
    ```
    source worker_env/bin/activate
    ```

- **Install Packages**
    ```
    pip install -r worker/requirements.txt
    ```

- **Start Worker**
    ```
    bash auto_restart_worker.sh --server-url <SERVER_WS_URL>/worker --target-hostname <API_HOSTNAME>
    ```