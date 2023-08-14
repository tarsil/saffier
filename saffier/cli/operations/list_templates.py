"""
Client to interact with Saffier models and migrations.
"""
import click

from saffier.cli.base import list_templates as template_list


@click.command(name="list-templates")
def list_templates() -> None:
    """
    Lists all the available templates available to Saffier
    """
    template_list()
