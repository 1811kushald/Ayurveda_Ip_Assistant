import os
from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator

from pgvector.django import VectorField, HnswIndex


class Document(models.Model):
    """Model representing an uploaded legal/regulatory PDF document in the corpus."""

    class Category(models.TextChoices):
        PATENT_LAW = 'patent_law', 'Patent Law'
        BIODIVERSITY = 'biodiversity', 'Biodiversity & Biological Diversity Act'
        DRUG_REG = 'drug_reg', 'Drugs & Cosmetics / AYUSH Regulations'
        FOOD_REG = 'food_reg', 'FSSAI / Food & Nutraceutical Regulations'
        GI = 'gi', 'Geographical Indications (GI)'
        GENERAL_IP = 'general_ip', 'General IP & Traditional Knowledge (TKDL)'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    title = models.CharField(max_length=255, help_text="e.g., The Patents Act, 1970")
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        default=Category.PATENT_LAW,
    )
    jurisdiction = models.CharField(max_length=100, default='India')
    date_enacted = models.DateField(null=True, blank=True, help_text="Date or year enacted")
    source_url = models.URLField(max_length=500, blank=True, help_text="Official source link")

    file = models.FileField(
        upload_to='documents/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
    )
    file_size_bytes = models.BigIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True, null=True)
    total_chunks = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_documents',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'document'
        verbose_name_plural = 'documents'

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    @property
    def file_size_display(self):
        """Human readable file size in KB or MB."""
        size = self.file_size_bytes
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"


class DocumentChunk(models.Model):
    """Model representing a semantic chunk extracted from a Document with vector embedding."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='chunks',
    )
    content = models.TextField()
    chunk_index = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    section_title = models.CharField(max_length=500, blank=True, default='')

    # Vector embedding: pgvector (768 dims)
    embedding = VectorField(dimensions=768)

    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document', 'chunk_index']
        verbose_name = 'document chunk'
        verbose_name_plural = 'document chunks'
        indexes = [
            HnswIndex(
                name='chunk_embedding_cosine_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            )
        ]

    def __str__(self):
        sec = f" [{self.section_title}]" if self.section_title else ""
        return f"{self.document.title} - Chunk #{self.chunk_index}{sec}"
