from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class ChatPageView(LoginRequiredMixin, TemplateView):
    """Renders the chat page shell only - no chat logic lives in Django.
    The page's JS talks to llm_service (FastAPI) directly over SSE, per
    the 2026-08-03 architecture decision that Django doesn't own the
    conversational-AI bounded context.
    """

    template_name = "chat/chat.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["llm_service_url"] = settings.LLM_SERVICE_URL
        return context
