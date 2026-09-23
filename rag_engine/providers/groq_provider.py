"""
Groq LLM provider using LangChain's ChatGroq wrapper.
Uses the free Qwen model (qwen-qwq-32b) for IP/Ayurveda guidance.
"""
import logging
import os
from typing import Any

from rag_engine.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'qwen-qwq-32b'
DEFAULT_TEMPERATURE = 0.1  # Low temp for factual legal/IP responses
DEFAULT_MAX_TOKENS = 2048


class GroqLLMProvider(BaseLLMProvider):
    """
    LLM provider backed by Groq's free inference API.

    Uses LangChain ChatGroq for structured prompting, token counting,
    and clean error handling.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._llm = None

    def _get_llm(self):
        """Lazy-initialize the ChatGroq instance."""
        if self._llm is None:
            from langchain_groq import ChatGroq

            api_key = os.environ.get('GROQ_API_KEY', '')
            if not api_key:
                raise ValueError(
                    'GROQ_API_KEY is not set. '
                    'Please add it to your .env file.'
                )

            self._llm = ChatGroq(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=api_key,
            )
        return self._llm

    def generate(self, prompt: str, context: str, **kwargs) -> dict:
        """
        Generate a response given a system prompt and context.

        Args:
            prompt: The full system + user prompt text.
            context: The assembled context from retrieved chunks.

        Returns:
            dict with keys: 'content', 'model', 'input_tokens', 'output_tokens'
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = self._get_llm()

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=context),
        ]

        try:
            response = llm.invoke(messages)

            # Extract token usage from response metadata
            usage = getattr(response, 'usage_metadata', {}) or {}
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)

            logger.info(
                'Groq (%s) — %d input tokens, %d output tokens.',
                self.model,
                input_tokens,
                output_tokens,
            )

            return {
                'content': response.content,
                'model': self.model,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            }

        except Exception as e:
            logger.error('Groq LLM generation failed: %s', str(e))
            raise

    def get_model_name(self) -> str:
        """Return the model name being used."""
        return self.model
