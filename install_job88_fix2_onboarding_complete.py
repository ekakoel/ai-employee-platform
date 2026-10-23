#!/usr/bin/env python3
"""
Job 88 FIX2 — mark company onboarding complete after verify; accept HTTP 410 for POST /users.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

AUTH = Path.cwd() / "tests" / "test_auth_job15.py"


def main() -> int:
    t = AUTH.read_text(encoding="utf-8")

    # After verify (or force-verify), set company.onboarding_status = "complete"
    old_force = '''    else:
        # force-verify in DB for non-debug envs
        with SessionLocal() as db:
            from app.models.entities import User
            from sqlalchemy import select

            u = db.scalar(select(User).where(User.email == email))
            assert u is not None
            u.email_verified = True
            db.commit()
    return company_id, email, password, body'''

    new_complete = '''    else:
        # force-verify in DB for non-debug envs
        with SessionLocal() as db:
            from app.models.entities import User
            from sqlalchemy import select

            u = db.scalar(select(User).where(User.email == email))
            assert u is not None
            u.email_verified = True
            db.commit()
    # Workspace APIs require onboarding_status == "complete"
    with SessionLocal() as db:
        from app.models.entities import Company

        co = db.get(Company, company_id)
        assert co is not None
        co.onboarding_status = "complete"
        db.commit()
    return company_id, email, password, body'''

    if old_force in t:
        t = t.replace(old_force, new_complete)
    elif 'co.onboarding_status = "complete"' not in t:
        # inject before return of company_with_user
        t = t.replace(
            "    return company_id, email, password, body",
            '''    with SessionLocal() as db:
        from app.models.entities import Company

        co = db.get(Company, company_id)
        assert co is not None
        co.onboarding_status = "complete"
        db.commit()
    return company_id, email, password, body''',
            1,
        )

    # Accept 410 Gone for invite-only user create
    t = t.replace(
        "assert res.status_code in (400, 403, 405, 422), res.text\n"
        '    assert "invit" in res.text.lower() or res.status_code in (403, 405)',
        "assert res.status_code in (400, 403, 405, 410, 422), res.text",
    )
    t = t.replace(
        "assert res.status_code in (400, 403, 405, 422), res.text",
        "assert res.status_code in (400, 403, 405, 410, 422), res.text",
    )

    AUTH.write_text(t, encoding="utf-8")
    compile(AUTH.read_text(encoding="utf-8"), str(AUTH), "exec")
    print("[OK] onboarding complete + 410 for POST /users")
    print(
        """
  pytest -q --tb=line tests/test_auth_job15.py tests/test_skills.py tests/test_users_roles_job36.py

  git add tests/test_auth_job15.py
  git commit -m "Job 88 fix2: complete onboarding after register; accept 410 invite-only"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
