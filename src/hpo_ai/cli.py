"""CLI interface for hpo-ai."""

import typer
from typing_extensions import Annotated

app = typer.Typer(help="hpo-ai: AI-powered pipeline for harmonising chemical phenotypes in the Human Phenotype Ontology (HPO)")


@app.command()
def run(
    name: Annotated[str, typer.Option(help="Name of the person to greet")],
):
    typer.echo(f"Hello, {name}!")

def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
