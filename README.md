## Deploy Server in Cloudron

```
docker build -t nathaniels32/reverse-proxy-tunnel:latest .
```

```
docker push nathaniels32/reverse-proxy-tunnel:latest
```

```
cloudron install --image nathaniels32/reverse-proxy-tunnel:latest
```

```
reverse-proxy-tunnel.3d-medico.com
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
    bash auto_restart_worker.sh --server-url <SERVER_WS_URL>/worker --target-hostname <API_HOSTNAME> --server-api-key <API_KEY_OPTIONAL>
    ```