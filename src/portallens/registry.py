"""Portal plugin registry.

Plugins register their :class:`Portal` subclass against a
:class:`PortalType`. The CLI uses this to dispatch a URL to the right
analyzer. Today only ``captive_wifi`` is registered; future plugins
(``web_auth``, ``payment``, ``isp``) will register themselves the same
way on import.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from portallens.portal import Portal, PortalType

_REGISTRY: dict[PortalType, type[Portal]] = {}

_P = TypeVar("_P", bound=Portal)


def register_portal(portal_type: PortalType) -> Callable[[type[_P]], type[_P]]:
    """Class decorator — register a :class:`Portal` subclass.

    Usage::

        @register_portal(PortalType.CAPTIVE_WIFI)
        class CaptiveWifiPortal(Portal):
            portal_type = PortalType.CAPTIVE_WIFI
            def analyze(self, ctx): ...
    """

    def decorator(cls: type[_P]) -> type[_P]:
        if not issubclass(cls, Portal):
            raise TypeError(f"{cls.__name__} must subclass Portal")
        cls.portal_type = portal_type
        _REGISTRY[portal_type] = cls
        return cls

    return decorator


def get_portal_class(portal_type: PortalType) -> type[Portal]:
    """Look up a registered :class:`Portal` subclass.

    Raises :class:`KeyError` if no plugin has registered for that type.
    Importing :mod:`portallens.plugins.captive_wifi` is what registers
    the captive Wi-Fi analyzer — the CLI does this on startup.
    """

    if portal_type not in _REGISTRY:
        raise KeyError(
            f"no Portal registered for {portal_type!r}. "
            f"Did you import the plugin module?"
        )
    return _REGISTRY[portal_type]


def registered_types() -> list[PortalType]:
    """Return all portal types with a registered analyzer."""

    return list(_REGISTRY)
