import nox

nox.options.default_venv_backend = "uv|venv"


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13"])
def run_cli(session):
    """Make sure the CLI runs correctly"""
    session.install(".")
    session.run("dbt-autofix", "--help")


@nox.session(python=["3.13"])
def check_latest_schema(session):
    """Make sure the CLI runs correctly"""
    session.install(".")
    session.run("dbt-autofix", "print-fields-matrix")


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13"])
def pytest(session):
    """Run the tests"""
    session.install(".[test]")
    session.run("pytest")
