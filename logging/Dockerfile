FROM nginx:1.31-alpine
RUN apk add --no-cache python3 \
    && sed -i '/access_log.*main;/d' /etc/nginx/nginx.conf
COPY umami-tracking.conf /etc/nginx/snippets/umami-tracking.conf
COPY redactor.py /usr/local/bin/redact-nginx.py
ENTRYPOINT ["python3", "-u", "/usr/local/bin/redact-nginx.py"]
CMD ["nginx", "-g", "daemon off;"]
