import typer
from rich.console import Console

from sports_engine.core.config import load_config
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate

app = typer.Typer(help="Warehouse lifecycle commands.")
console = Console()


@app.command("migrate")
def migrate_command() -> None:
    config = load_config()
    connection = connect(config.database_path)
    applied = migrate(connection)
    connection.close()
    console.print(f"Applied migrations: {applied or 'none (current)'}")
