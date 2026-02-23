"""
Utility functions for AAS2PDDL.
"""

import re
from typing import Optional
from basyx.aas import model


def sanitizePddlName(name: str) -> str:
    """Convert a name to a valid PDDL identifier.

    PDDL names may only contain lowercase letters, digits, underscores, and hyphens.

    Args:
        name: The name to convert

    Returns:
        A valid PDDL identifier
    """
    # Replace spaces and special characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Collapse multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Strip leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Lowercase
    sanitized = sanitized.lower()
    # Fallback if empty
    if not sanitized:
        sanitized = "domain"
    return sanitized


def getMlpValue(mlp: model.MultiLanguageProperty, preferLang: str = 'en') -> Optional[str]:
    """Extract text from a MultiLanguageProperty with language preference.

    BaSyx SDK 2.x: MultiLanguageTextType is dict-like with .get() method.

    Args:
        mlp: The MultiLanguageProperty
        preferLang: Preferred language (default: 'en')

    Returns:
        The extracted text or None
    """
    if not mlp.value:
        return None

    # BaSyx SDK 2.x: MultiLanguageTextType has .get() method
    if hasattr(mlp.value, 'get'):
        result = mlp.value.get(preferLang)
        if result:
            return result
        # Fallback: try other languages
        for lang in ['en', 'de']:
            result = mlp.value.get(lang)
            if result:
                return result
        # Fallback: first available language
        if hasattr(mlp.value, 'values'):
            values = list(mlp.value.values())
            if values:
                return values[0]

    # Fallback: direct string return if possible
    if isinstance(mlp.value, str):
        return mlp.value

    return None


def derivePredicateNameFromIdShort(idShort: str) -> str:
    """Derive PDDL predicate name from idShort.

    Args:
        idShort: The idShort (e.g. "DataElementType_On" or "Predicate_Loaded")

    Returns:
        The derived name (e.g. "on" or "loaded")
    """
    if idShort.startswith('DataElementType_'):
        return idShort[len('DataElementType_'):].lower()
    elif idShort.startswith('Predicate_'):
        return idShort[len('Predicate_'):].lower()
    else:
        return idShort.lower()
