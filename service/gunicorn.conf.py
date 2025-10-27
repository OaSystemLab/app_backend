# gunicorn.conf.py
from datetime import datetime
import os

# 폴더 생성 
if not os.path.exists("/oasiss/log/gunicorn"):
    os.makedirs("/oasiss/log/gunicorn")

bind = "0.0.0.0:6500" 
workers = 2
worker_class = "uvicorn.workers.UvicornWorker" 
reload = True
accesslog = f"/oasiss/log/gunicorn/access_{datetime.now().strftime('%Y-%m-%d_%H')}.log" 
errorlog =  f"/oasiss/log/gunicorn/error_{datetime.now().strftime('%Y-%m-%d_%H')}.log" 
loglevel = "info"

