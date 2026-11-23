"""``manage.py diary-push`` under the spelling the runbook uses.

Django names a management command after its module, and a Python module cannot
be imported through a name containing a dash -- so the implementation lives in
``diary_push.py`` and this file exists for the hyphen. ``get_commands()`` finds
it because it lists files, and ``importlib`` imports a dash-named module
happily; both spellings therefore run the same ``Command``.
"""

from .diary_push import Command  # noqa: F401  (Django looks the name up here)
