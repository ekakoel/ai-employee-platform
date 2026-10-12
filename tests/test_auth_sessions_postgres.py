"""Opt-in actual PostgreSQL concurrency. Never target an application database.

Set AUTH_TEST_POSTGRES_URL to an existing disposable database whose name starts
with aiep_auth_test_. Each test creates a random isolated schema; schemas are
retained for inspection, not dropped automatically. Run this file separately.
"""

import os

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from test_auth_sessions_isolated import (
    isolated, no_application_engine, stored_password,
    test_parallel_refresh_has_one_winner_and_replay_revocation,
    test_parallel_reset_has_one_winner,
    test_parallel_refresh_reset_cannot_restore_old_credentials,
    test_parallel_login_reset_leaves_no_old_credential_session,
    test_parallel_refresh_logout_does_not_restore_session,
    test_parallel_refresh_password_change_cannot_restore_session,
)


@pytest.fixture()
def postgres_test_url():
    raw = os.environ.get("AUTH_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Dedicated disposable PostgreSQL URL not provided")
    try:
        url = make_url(raw)
    except ArgumentError:
        pytest.fail("Invalid disposable PostgreSQL URL", pytrace=False)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").startswith("aiep_auth_test_"):
        pytest.fail("Only a dedicated aiep_auth_test_ PostgreSQL database is allowed", pytrace=False)
    return raw
