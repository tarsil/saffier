"""
Client to interact with Saffier models and migrations.
"""

from sayer import command

from saffier.cli.base import list_templates as template_list


@command
def list_templates() -> None:
    """
    Lists all the available templates available to Saffier
    """
    template_list()
