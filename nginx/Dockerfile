FROM nginx:1.27-alpine

# Setup proxy app
RUN apk add --no-cache bash python3 py3-pip py3-flask py3-requests
COPY proxy.py /opt/proxy.py

# Setup nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Entrypoint
COPY entrypoint /entrypoint.proxy
ENTRYPOINT ["/entrypoint.proxy"]
