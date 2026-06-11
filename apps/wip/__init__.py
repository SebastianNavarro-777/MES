"""WIP (Work-In-Process) bounded context.

Tracks units in process at every route step of every active manufacturing
order, and publishes ``wip.updated`` domain events to the ``wip.events`` stream
so downstream contexts (OEE, dashboards) can react without coupling synchronously
to ``wip``.
"""
