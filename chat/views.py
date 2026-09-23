import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponseBadRequest
from .models import Conversation, Message
from .forms import ChatMessageForm
from rag_engine.pipeline import query_pipeline

logger = logging.getLogger(__name__)


@login_required
def index_view(request):
    """Main chat view. Opens the most recent conversation or initializes a new one."""
    conversations = request.user.conversations.all()
    conversation = conversations.first()

    if not conversation:
        conversation = Conversation.objects.create(
            user=request.user,
            title='New Conversation',
        )
        conversations = request.user.conversations.all()

    messages = conversation.messages.all()
    form = ChatMessageForm()

    context = {
        'conversation': conversation,
        'messages': messages,
        'conversations': conversations,
        'form': form,
    }
    return render(request, 'chat/chat.html', context)


@login_required
def detail_view(request, conversation_id):
    """View an existing conversation thread by ID."""
    conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    conversations = request.user.conversations.all()
    messages = conversation.messages.all()
    form = ChatMessageForm()

    context = {
        'conversation': conversation,
        'messages': messages,
        'conversations': conversations,
        'form': form,
    }
    return render(request, 'chat/chat.html', context)


@login_required
def new_view(request):
    """Create a new conversation and redirect to it."""
    conversation = Conversation.objects.create(
        user=request.user,
        title='New Conversation',
    )
    return redirect('chat:detail', conversation_id=conversation.id)


@login_required
@require_POST
def send_message_view(request, conversation_id):
    """
    Handle query submission via HTMX or standard POST.
    Runs RAG pipeline (retrieve -> rerank -> generate) and returns message partial.
    """
    conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    form = ChatMessageForm(request.POST)

    if not form.is_valid():
        return HttpResponseBadRequest("Invalid message query.")

    user_query = form.cleaned_data['content'].strip()
    category_filter = form.cleaned_data.get('category') or None

    if not user_query:
        return HttpResponseBadRequest("Query cannot be empty.")

    # 1. Save user message
    user_msg = Message.objects.create(
        conversation=conversation,
        sender=Message.Sender.USER,
        content=user_query,
    )

    # 2. Run RAG query pipeline
    try:
        rag_result = query_pipeline(
            user_query=user_query,
            category_filter=category_filter,
        )
    except Exception as e:
        logger.error(f"RAG pipeline error for user query '{user_query}': {str(e)}", exc_info=True)
        rag_result = {
            'answer': f"⚠️ An error occurred while generating the response: {str(e)}. Please try again or rephrase your query.",
            'sources': [],
            'model': 'error',
            'input_tokens': 0,
            'output_tokens': 0,
            'elapsed_seconds': 0.0,
        }

    # 3. Save assistant message
    assistant_msg = Message.objects.create(
        conversation=conversation,
        sender=Message.Sender.ASSISTANT,
        content=rag_result['answer'],
        sources=rag_result.get('sources', []),
        model_name=rag_result.get('model', ''),
        token_count=rag_result.get('output_tokens', 0) + rag_result.get('input_tokens', 0),
        latency_seconds=rag_result.get('elapsed_seconds', 0.0),
    )

    # 4. Auto-update conversation title if still default
    if conversation.title == 'New Conversation':
        clean_title = user_query[:45].strip()
        if len(user_query) > 45:
            clean_title += '...'
        conversation.title = clean_title
        conversation.save(update_fields=['title', 'updated_at'])

    # 5. Return HTMX partial or redirect
    if request.htmx:
        context = {
            'user_msg': user_msg,
            'assistant_msg': assistant_msg,
            'conversation': conversation,
        }
        return render(request, 'chat/partials/message_pair.html', context)

    return redirect('chat:detail', conversation_id=conversation.id)


@login_required
@require_POST
def delete_view(request, conversation_id):
    """Delete a conversation thread."""
    conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    conversation.delete()
    return redirect('chat:index')


@login_required
@require_POST
def clear_view(request, conversation_id):
    """Clear all messages in a conversation."""
    conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    conversation.messages.all().delete()
    return redirect('chat:detail', conversation_id=conversation.id)
