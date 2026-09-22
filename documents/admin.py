from django.contrib import admin
from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'jurisdiction', 'status', 'total_chunks', 'file_size_display', 'uploaded_by', 'uploaded_at')
    list_filter = ('category', 'status', 'jurisdiction', 'uploaded_at')
    search_fields = ('title', 'source_url', 'error_message')
    readonly_fields = ('file_size_bytes', 'total_chunks', 'uploaded_at', 'updated_at')
    ordering = ('-uploaded_at',)

    def file_size_display(self, obj):
        return obj.file_size_display
    file_size_display.short_description = 'Size'


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'section_title', 'page_number', 'token_count', 'created_at')
    list_filter = ('document__category', 'page_number')
    search_fields = ('content', 'section_title', 'document__title')
    readonly_fields = ('created_at',)
    ordering = ('document', 'chunk_index')
