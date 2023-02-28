"""
Client to interact with Saffier models and migrations.
"""
import click

from saffier.migrations.base import list_templates as template_list


@click.command(name="list-templates")
def list_templates():
    template_list()
