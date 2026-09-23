from django.db import models
from django.conf import settings


class Conversation(models.Model):
    """Model representing a chat thread for a user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations',
    )
    title = models.CharField(max_length=255, default='New Conversation')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'conversation'
        verbose_name_plural = 'conversations'

    def __str__(self):
        return f"{self.title} ({self.user.email})"

    @property
    def message_count(self):
        return self.messages.count()

    @property
    def last_message(self):
        return self.messages.last()


class Message(models.Model):
    """Model representing an individual message in a Conversation."""

    class Sender(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.CharField(
        max_length=20,
        choices=Sender.choices,
        default=Sender.USER,
    )
    content = models.TextField()
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of source citations with document_title, section_title, page_number",
    )
    model_name = models.CharField(max_length=100, blank=True, default='')
    token_count = models.PositiveIntegerField(default=0)
    latency_seconds = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'message'
        verbose_name_plural = 'messages'

    def __str__(self):
        return f"[{self.get_sender_display()}] {self.content[:40]}..."
