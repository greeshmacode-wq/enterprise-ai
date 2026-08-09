from django import forms

from apps.documents.models import Document
from apps.documents.serializers import ALLOWED_EXTENSIONS


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Document title"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def clean_file(self):
        file = self.cleaned_data["file"]
        extension = file.name.rsplit(".", 1)[-1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                f"Unsupported file type '.{extension}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )
        return file
