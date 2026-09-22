from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    Allows switching between Groq, Gemini, OpenAI, etc.
    by implementing this interface.
    """

    @abstractmethod
    def generate(self, prompt: str, context: str, **kwargs) -> dict:
        """Generate a response given a prompt and context.
        
        Returns:
            dict with keys: 'content', 'model', 'input_tokens', 'output_tokens'
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model name being used."""
        pass
