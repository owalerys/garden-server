import click
from flask import g
from flask.cli import with_appcontext
from garden.model import Garden

def get_garden():
    if 'garden' not in g:
        g.garden = Garden()

    return g.garden

def refresh_garden():
    garden = get_garden()
    garden.refresh()

@click.command('get-garden')
@with_appcontext
def get_garden_command():
    """Create a test garden instance."""
    garden = get_garden()
    click.echo('Refreshed the garden.')

@click.command('iterate-garden')
@with_appcontext
def iterate_garden_command():
    """Run the garden interaction command."""
    get_garden()

    g.garden.iterate()

def disconnect_garden(e=None):
    if 'garden' in g:
        if g.garden.isIterator():
            g.garden.close()

def init_app(app):
    app.cli.add_command(get_garden_command)
    app.cli.add_command(iterate_garden_command)
    app.teardown_appcontext(disconnect_garden)
