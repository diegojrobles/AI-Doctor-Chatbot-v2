# Sensible defaults; tune for your CPU
bind = "0.0.0.0:8000"
workers = 2
worker_class = "uvicorn.workers.UvicornWorker"
wsgi_app = "app.main:app"
timeout = 90
graceful_timeout = 30
keepalive = 5

# Trust X-Forwarded-For / X-Forwarded-Proto from the proxy. Only Caddy can reach
# this process (the api container publishes no ports), so the headers cannot be
# spoofed by an outside caller. Without this, request.client.host is always the
# proxy address and every caller shares one rate-limit bucket.
forwarded_allow_ips = "*"
