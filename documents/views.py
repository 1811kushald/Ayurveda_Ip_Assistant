from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.decorators import role_required
from .models import Document
from .forms import DocumentUploadForm
from .tasks import dispatch_document_processing


@role_required('admin', 'super_admin')
def list_view(request):
    """View listing all documents in the corpus."""
    category_filter = request.GET.get('category')
    status_filter = request.GET.get('status')
    search_query = request.GET.get('q')

    documents = Document.objects.all()

    if category_filter:
        documents = documents.filter(category=category_filter)
    if status_filter:
        documents = documents.filter(status=status_filter)
    if search_query:
        documents = documents.filter(title__icontains=search_query)

    categories = Document.Category.choices
    statuses = Document.Status.choices

    has_processing = any(d.status in ('processing', 'pending') for d in documents)

    context = {
        'documents': documents,
        'categories': categories,
        'statuses': statuses,
        'selected_category': category_filter,
        'selected_status': status_filter,
        'search_query': search_query,
        'has_processing': has_processing,
    }
    return render(request, 'documents/document_list.html', context)


@role_required('admin', 'super_admin')
def upload_view(request):
    """View for uploading new PDF document to the corpus."""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.uploaded_by = request.user
            document.file_size_bytes = request.FILES['file'].size
            document.status = Document.Status.PENDING
            document.save()

            # Dispatch background processing pipeline asynchronously
            dispatch_document_processing(document.pk)

            messages.success(
                request,
                f"Document '{document.title}' uploaded successfully! Processing started in background."
            )
            return redirect('documents:detail', pk=document.pk)
        else:
            messages.error(request, "Error uploading document. Please check the form errors below.")
    else:
        form = DocumentUploadForm()

    return render(request, 'documents/document_upload.html', {'form': form})


@role_required('admin', 'super_admin')
def detail_view(request, pk):
    """View displaying document details, ingestion status, and metadata."""
    document = get_object_or_404(Document, pk=pk)
    return render(request, 'documents/document_detail.html', {'document': document})


@role_required('admin', 'super_admin')
def reprocess_view(request, pk):
    """View for manually re-triggering ingestion processing for a document."""
    document = get_object_or_404(Document, pk=pk)

    if request.method == 'POST':
        document.status = Document.Status.PENDING
        document.error_message = None
        document.save(update_fields=['status', 'error_message'])

        dispatch_document_processing(document.pk)
        messages.info(request, f"Reprocessing triggered for '{document.title}'.")
        return redirect('documents:detail', pk=document.pk)

    return redirect('documents:detail', pk=document.pk)


@role_required('admin', 'super_admin')
def delete_view(request, pk):
    """View for deleting a document from the corpus."""
    document = get_object_or_404(Document, pk=pk)

    if request.method == 'POST':
        title = document.title
        # Delete file from storage and record from database
        if document.file:
            document.file.delete(save=False)
        document.delete()
        messages.success(request, f"Document '{title}' deleted from corpus.")
        return redirect('documents:list')

    return render(request, 'documents/document_confirm_delete.html', {'document': document})
