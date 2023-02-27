"""
Client to interact with Saffier models and migrations.
"""
import click


@click.group()
def database():
    """Performs database migrations"""
    ...
