from django import forms
from .models import Document

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class DocumentUploadForm(forms.ModelForm):
    """Form for uploading PDF documents to the legal corpus."""

    class Meta:
        model = Document
        fields = ['title', 'category', 'jurisdiction', 'date_enacted', 'source_url', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., The Patents Act, 1970'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'jurisdiction': forms.TextInput(attrs={'class': 'form-control', 'value': 'India'}),
            'date_enacted': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'source_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://ipindia.gov.in/...'}),
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            # Check extension
            if not uploaded_file.name.lower().endswith('.pdf'):
                raise forms.ValidationError("Only PDF files are allowed.")
            # Check size
            if uploaded_file.size > MAX_FILE_SIZE_BYTES:
                raise forms.ValidationError(f"File size exceeds maximum limit of {MAX_FILE_SIZE_MB}MB.")
        return uploaded_file
