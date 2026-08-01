import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("enterprise_ai")

# Read config from Django settings with namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY_")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()