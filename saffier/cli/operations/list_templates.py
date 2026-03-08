"""
Client to interact with Saffier models and migrations.
"""

from sayer import command

from saffier.cli.base import list_templates as template_list


@command
def list_templates() -> None:
    """List all available migration repository templates.

    This exposes the same template inventory as `saffier.cli.base.list_templates`.
    """
    template_list()
