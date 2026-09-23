from django import forms
from documents.models import Document


class ChatMessageForm(forms.Form):
    """Form for submitting a question to the RAG chat query engine."""

    content = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'class': 'form-control shadow-sm',
                'rows': 2,
                'placeholder': 'Ask any question on Ayurvedic IP, Patents Act, TKDL, AYUSH, or Biodiversity...',
                'id': 'chat-input-textarea',
            }
        ),
        required=True,
        label='',
    )

    category = forms.ChoiceField(
        choices=[('', 'All Legal Domains')] + list(Document.Category.choices),
        required=False,
        widget=forms.Select(
            attrs={
                'class': 'form-select form-select-sm shadow-sm',
                'id': 'chat-category-select',
            }
        ),
        label='Filter Domain',
    )
