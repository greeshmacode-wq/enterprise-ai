import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("enterprise_ai")
print("Celery app initialized with name:", app.main)  # Debugging statement
# Read config from Django settings with namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY_")
app.autodiscover_tasks() # scans every app in INSTALLED_APPS, finds each app's tasks.py, and imports it. 