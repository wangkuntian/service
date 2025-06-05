import inspect
import operator
import types
from collections.abc import Callable
from typing import Any

_BUILTIN_MODULES = ('builtins', '__builtin__', '__builtins__', 'exceptions')


def get_method_self(method: Callable) -> Any | None:
    """Gets the ``self`` object attached to this method (or none)."""
    if not inspect.ismethod(method):
        return None
    try:
        return operator.attrgetter('__self__')(method)
    except AttributeError:
        return None


def get_callable_name(function):
    """Generate a name from callable.

    Tries to do the best to guess fully qualified callable name.
    """
    method_self = get_method_self(function)
    if method_self is not None:
        # This is a bound method.
        if isinstance(method_self, type):
            # This is a bound class method.
            im_class = method_self
        else:
            im_class = type(method_self)
        try:
            parts = (im_class.__module__, function.__qualname__)
        except AttributeError:
            parts = (im_class.__module__, im_class.__name__, function.__name__)
    elif inspect.ismethod(function) or inspect.isfunction(function):
        # This could be a function, a static method, a unbound method...
        try:
            parts = (function.__module__, function.__qualname__)
        except AttributeError:
            if hasattr(function, 'im_class'):
                # This is a unbound method, which exists only in python 2.x
                im_class = function.im_class
                parts = (
                    im_class.__module__,
                    im_class.__name__,
                    function.__name__,
                )
            else:
                parts = (function.__module__, function.__name__)
    else:
        im_class = type(function)
        if im_class is types.TypeType:
            im_class = function
        try:
            parts = (im_class.__module__, im_class.__qualname__)
        except AttributeError:
            parts = (im_class.__module__, im_class.__name__)
    return '.'.join(parts)


def get_class_name(obj, fully_qualified=True, truncate_builtins=True):
    """Get class name for object.

    If object is a type, returns name of the type. If object is a bound
    method or a class method, returns its ``self`` object's class name.
    If object is an instance of class, returns instance's class name.
    Else, name of the type of the object is returned. If fully_qualified
    is True, returns fully qualified name of the type. For builtin types,
    just name is returned. TypeError is raised if can't get class name from
    object.
    """
    if inspect.isfunction(obj):
        raise TypeError("Can't get class name.")

    if inspect.ismethod(obj):
        obj = get_method_self(obj)
    if not isinstance(obj, type):
        obj = type(obj)
    if truncate_builtins:
        try:
            built_in = obj.__module__ in _BUILTIN_MODULES
        except AttributeError:  # nosec
            pass
        else:
            if built_in:
                return obj.__name__
    if fully_qualified and hasattr(obj, '__module__'):
        return f'{obj.__module__}.{obj.__name__}'
    else:
        return obj.__name__
