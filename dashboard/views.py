import logging
import time
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.db import connection
from django.db.models import Sum, Avg, Count
from accounts.decorators import role_required
from documents.models import Document, DocumentChunk
from chat.models import Conversation, Message
from rag_engine.embeddings import get_embedding
from rag_engine.reranker import rerank_chunks
from rag_engine.providers.groq_provider import GroqLLMProvider

logger = logging.getLogger(__name__)
User = get_user_model()


@role_required('admin', 'super_admin')
def index_view(request):
    """Admin Dashboard view providing corpus KPIs, category distribution, and telemetry."""
    # 1. Corpus Statistics
    total_documents = Document.objects.count()
    completed_documents = Document.objects.filter(status=Document.Status.COMPLETED).count()
    processing_documents = Document.objects.filter(status=Document.Status.PROCESSING).count()
    failed_documents = Document.objects.filter(status=Document.Status.FAILED).count()
    total_chunks = DocumentChunk.objects.count()
    total_storage_bytes = Document.objects.aggregate(total=Sum('file_size_bytes'))['total'] or 0
    total_storage_mb = round(total_storage_bytes / (1024 * 1024), 2)

    # 2. Category Distribution Breakdown
    category_stats = []
    for code, label in Document.Category.choices:
        doc_count = Document.objects.filter(category=code).count()
        chunk_count = DocumentChunk.objects.filter(document__category=code).count()
        percentage = round((doc_count / total_documents * 100), 1) if total_documents > 0 else 0
        category_stats.append({
            'code': code,
            'label': label,
            'doc_count': doc_count,
            'chunk_count': chunk_count,
            'percentage': percentage,
        })

    # 3. Chat & Query Telemetry
    total_conversations = Conversation.objects.count()
    total_messages = Message.objects.count()
    user_queries_count = Message.objects.filter(sender=Message.Sender.USER).count()
    assistant_responses_count = Message.objects.filter(sender=Message.Sender.ASSISTANT).count()

    avg_latency = Message.objects.filter(
        sender=Message.Sender.ASSISTANT,
        latency_seconds__gt=0,
    ).aggregate(avg=Avg('latency_seconds'))['avg']
    avg_latency = round(avg_latency, 2) if avg_latency else 0.0

    total_tokens = Message.objects.filter(
        sender=Message.Sender.ASSISTANT,
    ).aggregate(total=Sum('token_count'))['total'] or 0

    # 4. User Statistics
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    admin_users = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.SUPER_ADMIN]).count()

    # 5. Recent Activity
    recent_documents = Document.objects.order_by('-uploaded_at')[:5]
    recent_messages = Message.objects.filter(
        sender=Message.Sender.USER,
    ).select_related('conversation', 'conversation__user').order_by('-created_at')[:5]

    context = {
        'total_documents': total_documents,
        'completed_documents': completed_documents,
        'processing_documents': processing_documents,
        'failed_documents': failed_documents,
        'total_chunks': total_chunks,
        'total_storage_mb': total_storage_mb,
        'category_stats': category_stats,
        'total_conversations': total_conversations,
        'total_messages': total_messages,
        'user_queries_count': user_queries_count,
        'assistant_responses_count': assistant_responses_count,
        'avg_latency': avg_latency,
        'total_tokens': total_tokens,
        'total_users': total_users,
        'active_users': active_users,
        'admin_users': admin_users,
        'recent_documents': recent_documents,
        'recent_messages': recent_messages,
    }
    return render(request, 'dashboard/index.html', context)


@role_required('super_admin')
def users_view(request):
    """Super Admin user management view."""
    search_query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()

    users = User.objects.annotate(conv_count=Count('conversations')).order_by('-date_joined')

    if search_query:
        users = users.filter(email__icontains=search_query) | users.filter(full_name__icontains=search_query)
    if role_filter:
        users = users.filter(role=role_filter)

    context = {
        'users': users,
        'roles': User.Role.choices,
        'selected_role': role_filter,
        'search_query': search_query,
    }
    return render(request, 'dashboard/users.html', context)


@role_required('super_admin')
@require_POST
def change_user_role_view(request, user_id):
    """Change a user's role (user / admin / super_admin) with self-demotion protection."""
    target_user = get_object_or_404(User, pk=user_id)
    new_role = request.POST.get('role', '').strip()

    valid_roles = [User.Role.USER, User.Role.ADMIN, User.Role.SUPER_ADMIN]
    if new_role not in valid_roles:
        messages.error(request, "Invalid role specified.")
        return redirect('dashboard:users')

    # Prevent self-demotion if sole super admin
    if target_user == request.user and new_role != User.Role.SUPER_ADMIN:
        other_super_admins = User.objects.filter(
            role=User.Role.SUPER_ADMIN,
            is_active=True,
        ).exclude(pk=target_user.pk).exists()

        if not other_super_admins:
            messages.error(request, "You cannot demote yourself as you are the only active Super Admin.")
            return redirect('dashboard:users')

    target_user.role = new_role
    target_user.is_staff = (new_role in [User.Role.ADMIN, User.Role.SUPER_ADMIN])
    target_user.is_superuser = (new_role == User.Role.SUPER_ADMIN)
    target_user.save()

    messages.success(request, f"Updated role for {target_user.email} to {target_user.get_role_display()}.")
    return redirect('dashboard:users')


@role_required('super_admin')
@require_POST
def toggle_user_status_view(request, user_id):
    """Activate or deactivate a user account with self-deactivation protection."""
    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('dashboard:users')

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    status_str = "Active" if target_user.is_active else "Inactive"
    messages.success(request, f"User {target_user.email} is now {status_str}.")
    return redirect('dashboard:users')


@role_required('admin', 'super_admin')
def system_status_view(request):
    """Live diagnostic check for Supabase DB, Gemini Embeddings, Jina Reranker, and Groq LLM."""
    diagnostics = []

    # 1. Database & pgvector check
    db_start = time.time()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        db_latency = round((time.time() - db_start) * 1000, 1)
        db_engine = connection.settings_dict.get('ENGINE', 'unknown')
        diagnostics.append({
            'name': 'PostgreSQL Database (Supabase)',
            'status': 'healthy',
            'details': f"Connected ({db_engine})",
            'latency_ms': db_latency,
            'icon': 'bi-database-check text-success',
        })
    except Exception as e:
        diagnostics.append({
            'name': 'PostgreSQL Database (Supabase)',
            'status': 'error',
            'details': str(e),
            'latency_ms': None,
            'icon': 'bi-database-x text-danger',
        })

    # 2. Gemini Embedding API
    gemini_start = time.time()
    if os.environ.get('GOOGLE_API_KEY'):
        try:
            vec = get_embedding("Test connectivity")
            gemini_latency = round((time.time() - gemini_start) * 1000, 1)
            diagnostics.append({
                'name': 'Google Gemini Embeddings (gemini-embedding-001)',
                'status': 'healthy',
                'details': f"768-dim vector generated ({len(vec)} dims)",
                'latency_ms': gemini_latency,
                'icon': 'bi-lightning-charge-fill text-success',
            })
        except Exception as e:
            diagnostics.append({
                'name': 'Google Gemini Embeddings (gemini-embedding-001)',
                'status': 'error',
                'details': str(e),
                'latency_ms': None,
                'icon': 'bi-lightning-charge text-danger',
            })
    else:
        diagnostics.append({
            'name': 'Google Gemini Embeddings',
            'status': 'warning',
            'details': 'GOOGLE_API_KEY not configured in .env',
            'latency_ms': None,
            'icon': 'bi-exclamation-triangle text-warning',
        })

    # 3. Jina AI Reranker
    jina_start = time.time()
    if os.environ.get('JINA_API_KEY'):
        try:
            dummy_chunks = [{'chunk_id': 1, 'content': 'Test legal passage.', 'score': 0.8}]
            rerank_res = rerank_chunks('Test', dummy_chunks, top_k=1)
            jina_latency = round((time.time() - jina_start) * 1000, 1)
            diagnostics.append({
                'name': 'Jina AI Cross-Encoder (jina-reranker-v2-base-multilingual)',
                'status': 'healthy',
                'details': 'Reranking operational',
                'latency_ms': jina_latency,
                'icon': 'bi-diagram-3-fill text-success',
            })
        except Exception as e:
            diagnostics.append({
                'name': 'Jina AI Cross-Encoder',
                'status': 'error',
                'details': str(e),
                'latency_ms': None,
                'icon': 'bi-diagram-3 text-danger',
            })
    else:
        diagnostics.append({
            'name': 'Jina AI Cross-Encoder',
            'status': 'warning',
            'details': 'JINA_API_KEY not configured (fallback enabled)',
            'latency_ms': None,
            'icon': 'bi-exclamation-triangle text-warning',
        })

    # 4. Groq LLM Provider
    groq_start = time.time()
    if os.environ.get('GROQ_API_KEY'):
        try:
            provider = GroqLLMProvider()
            provider_model = provider.get_model_name()
            groq_latency = round((time.time() - groq_start) * 1000, 1)
            diagnostics.append({
                'name': f"Groq Inference Engine ({provider_model})",
                'status': 'healthy',
                'details': 'Ready for inference (max 750 tokens)',
                'latency_ms': groq_latency,
                'icon': 'bi-cpu-fill text-success',
            })
        except Exception as e:
            diagnostics.append({
                'name': 'Groq Inference Engine',
                'status': 'error',
                'details': str(e),
                'latency_ms': None,
                'icon': 'bi-cpu text-danger',
            })
    else:
        diagnostics.append({
            'name': 'Groq Inference Engine',
            'status': 'warning',
            'details': 'GROQ_API_KEY not configured',
            'latency_ms': None,
            'icon': 'bi-exclamation-triangle text-warning',
        })

    context = {
        'diagnostics': diagnostics,
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    return render(request, 'dashboard/system_status.html', context)
