import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic.edit import FormView

from apps.documents.forms import DocumentUploadForm
from apps.documents.services import visible_documents
from apps.documents.tasks import process_document

logger = logging.getLogger(__name__)


class DocumentUploadView(LoginRequiredMixin, FormView):
    template_name = "documents/upload.html"
    form_class = DocumentUploadForm
    success_url = reverse_lazy("documents:upload")

    def get_form_kwargs(self):
        # FormView doesn't bind request.FILES by default - without this,
        # file uploads would silently validate as "this field is required".
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST":
            kwargs["files"] = self.request.FILES
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["documents"] = visible_documents(self.request.user).order_by("-created_at")
        return context

    def form_valid(self, form):
        document = form.save(commit=False)
        document.uploaded_by = self.request.user
        document.department = self.request.user.department  # department="Finance", department = "Engineering"
        document.save()

        process_document.delay(document.id) #{"task": "apps.documents.tasks.process_document", "id": "<random-uuid>", "args": [5], "kwargs": {}}  publishes it to Redis at CELERY_BROKER_URL, on Celery's default queue (literally named "celery").
        logger.info("Document %s uploaded by %s, queued for processing", document.id, self.request.user.first_name)
        messages.success(self.request, f'"{document.title}" uploaded - processing now.')
        return super().form_valid(form) # redirect to success_url
