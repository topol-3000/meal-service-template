import pytest
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.integration


def test_models_match_migrations(alembic_config: Config) -> None:
    """Fails when a model changed without a migration: run `make migration name=...`."""
    command.check(alembic_config)


def test_migrations_downgrade_and_upgrade_again(alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
