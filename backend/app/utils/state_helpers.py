"""
State helper utilities for safely accessing dictionary values.

Problem: Python's dict.get(key, default) returns `default` ONLY when key is absent.
If the key exists but value is None, it returns None, not the default.

This module provides safe_get functions that return the default when value is None.
"""

from typing import Any, Dict, List, Optional, TypeVar, Union

T = TypeVar('T')


def safe_get(state: Dict[str, Any], key: str, default: T = None) -> Union[Any, T]:
    """
    Safely get a value from state, returning default if value is None or missing.
    
    Unlike dict.get(), this returns the default even when the key exists but value is None.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default value to return if key is missing or value is None
        
    Returns:
        The value if it exists and is not None, otherwise the default
        
    Example:
        >>> state = {"a": 1, "b": None, "c": []}
        >>> safe_get(state, "a", 0)  # Returns 1
        >>> safe_get(state, "b", 0)  # Returns 0 (not None!)
        >>> safe_get(state, "c", [1])  # Returns [] (empty list is not None)
        >>> safe_get(state, "d", 0)  # Returns 0 (key missing)
    """
    value = state.get(key)
    if value is None:
        return default
    return value


def safe_get_int(state: Dict[str, Any], key: str, default: int = 0) -> int:
    """
    Safely get an integer from state.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default integer to return
        
    Returns:
        Integer value, or default if missing/None/not convertible
    """
    value = state.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_get_float(state: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """
    Safely get a float from state.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default float to return
        
    Returns:
        Float value, or default if missing/None/not convertible
    """
    value = state.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_get_bool(state: Dict[str, Any], key: str, default: bool = False) -> bool:
    """
    Safely get a boolean from state.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default boolean to return
        
    Returns:
        Boolean value, or default if missing/None
    """
    value = state.get(key)
    if value is None:
        return default
    return bool(value)


def safe_get_list(state: Dict[str, Any], key: str, default: Optional[List] = None) -> List:
    """
    Safely get a list from state.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default list to return (defaults to empty list)
        
    Returns:
        List value, or default if missing/None
        
    Note:
        Always returns a new list if default is used to prevent mutation issues
    """
    if default is None:
        default = []
    
    value = state.get(key)
    if value is None:
        return list(default)  # Return a copy to prevent mutation
    
    if isinstance(value, list):
        return value
    
    # Try to convert to list
    try:
        return list(value)
    except (TypeError, ValueError):
        return list(default)


def safe_get_str(state: Dict[str, Any], key: str, default: str = "") -> str:
    """
    Safely get a string from state.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default string to return
        
    Returns:
        String value, or default if missing/None
    """
    value = state.get(key)
    if value is None:
        return default
    return str(value)


def safe_get_dict(state: Dict[str, Any], key: str, default: Optional[Dict] = None) -> Dict:
    """
    Safely get a dictionary from state.
    
    Args:
        state: The state dictionary
        key: The key to look up
        default: Default dict to return (defaults to empty dict)
        
    Returns:
        Dict value, or default if missing/None
    """
    if default is None:
        default = {}
    
    value = state.get(key)
    if value is None:
        return dict(default)  # Return a copy to prevent mutation
    
    if isinstance(value, dict):
        return value
    
    return dict(default)
