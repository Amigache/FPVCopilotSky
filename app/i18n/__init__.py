"""
Backend internationalization module for FPVCopilotSky.
Handles message translation based on Accept-Language header.
"""

import json
import os
from typing import Dict, Any, Optional
from functools import lru_cache


class I18nManager:
    """Manages translations for API messages."""
    
    def __init__(self):
        self.translations: Dict[str, Dict[str, Any]] = {}
        self._load_translations()
    
    def _load_translations(self):
        """Load all translation files from the i18n directory."""
        i18n_dir = os.path.dirname(os.path.abspath(__file__))
        
        for lang in ['en', 'es']:
            file_path = os.path.join(i18n_dir, f'{lang}.json')
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.translations[lang] = json.load(f)
            except Exception as e:
                print(f"Error loading {lang}.json: {e}")
    
    def get_language_from_accept_language(self, accept_language: Optional[str]) -> str:
        """
        Extract language code from Accept-Language header.
        
        Args:
            accept_language: Accept-Language header value (e.g., "es-ES,es;q=0.9,en;q=0.8")
        
        Returns:
            Language code: 'es', 'en', or default 'en'
        """
        if not accept_language:
            return 'en'
        
        # Parse Accept-Language header
        # Format: en-US,en;q=0.9,es;q=0.8
        languages = accept_language.split(',')
        for lang_range in languages:
            lang_code = lang_range.split(';')[0].strip().lower()
            # Extract language part only (en from en-US)
            lang_only = lang_code.split('-')[0]
            
            if lang_only in self.translations:
                return lang_only
        
        return 'en'
    
    def translate(self, key: str, language: str = 'en', **kwargs) -> str:
        """
        Get translated message by key.
        
        Args:
            key: Translation key in format "category.key" (e.g., "serial.preferences_saved")
            language: Language code ('es' or 'en'). Defaults to 'en'
            **kwargs: Variables to format in the message (e.g., error="Some error")
        
        Returns:
            Translated message string
        """
        # Ensure valid language
        if language not in self.translations:
            language = 'en'
        
        # Navigate nested dictionary
        keys = key.split('.')
        value = self.translations[language]
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Return fallback to English if key not found
                return self._get_fallback(key, **kwargs)
        
        # Format message with provided variables
        if isinstance(value, str) and kwargs:
            try:
                return value.format(**kwargs)
            except KeyError:
                # If formatting fails, return unformatted
                return value
        
        return value if isinstance(value, str) else str(value)
    
    def _get_fallback(self, key: str, **kwargs) -> str:
        """Get English fallback translation."""
        keys = key.split('.')
        value = self.translations.get('en', {})
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Return key itself if translation not found
                return key
        
        # Format fallback message
        if isinstance(value, str) and kwargs:
            try:
                return value.format(**kwargs)
            except KeyError:
                return value
        
        return value if isinstance(value, str) else str(value)


# Global instance
_i18n_manager: Optional[I18nManager] = None


def get_i18n_manager() -> I18nManager:
    """Get or create the global I18nManager instance."""
    global _i18n_manager
    if _i18n_manager is None:
        _i18n_manager = I18nManager()
    return _i18n_manager


def translate(key: str, language: str = 'en', **kwargs) -> str:
    """
    Convenience function to translate a message.
    
    Args:
        key: Translation key (e.g., "serial.preferences_saved")
        language: Language code ('es' or 'en')
        **kwargs: Variables to format in the message
    
    Returns:
        Translated message string
    """
    return get_i18n_manager().translate(key, language, **kwargs)


def get_language_from_request(request) -> str:
    """
    Get language preference from FastAPI request.
    
    Supports:
    1. Accept-Language header (HTTP standard)
    2. ?language=es query parameter (fallback)
    3. Defaults to 'en' if neither is provided
    
    Args:
        request: FastAPI Request object
    
    Returns:
        Language code ('es' or 'en')
    """
    manager = get_i18n_manager()
    
    # Try query parameter first
    language = request.query_params.get('language')
    if language in manager.translations:
        return language
    
    # Try Accept-Language header
    accept_language = request.headers.get('accept-language')
    return manager.get_language_from_accept_language(accept_language)
