#!/usr/bin/env python3
"""
Job 96 fix — 
1) 403 "Complete company profile before using the workspace" blocked ALL /companies/*
   including GET company/agents needed to finish onboarding (chicken-and-egg).
2) Brand pupil transform NaN when orb has zero size after login.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
AUTH = ROOT / "app" / "core" / "auth.py"
JS = ROOT / "app" / "static" / "workspace" / "app.js"

NEW_GET_AUTH = '''
def get_authenticated_user_id(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    """Supply a verified ID to existing company handlers and their audit calls.

    While onboarding is incomplete, allow the minimum set of company routes
    needed to finish setup (read company/agents, update profile, hire agents).
    Everything else stays blocked until onboarding_status == complete.
    """
    if request.url.path.startswith("/api/v1/companies/"):
        company = db.get(Company, user.company_id)
        if company and company.onboarding_status != "complete":
            path = request.url.path
            method = request.method.upper()
            cid = company.id
            # Exact company resource
            company_path = f"/api/v1/companies/{cid}"
            allowed = False
            if method == "GET":
                # reads required by workspace shell + onboarding wizard
                allowed = True
            elif method in {"PATCH", "PUT"} and path.rstrip("/") == company_path:
                allowed = True
            elif method == "POST" and (
                f"/companies/{cid}/agents/" in path and path.rstrip("/").endswith("/hire")
                or path.rstrip("/").endswith(f"/companies/{cid}/agents")
            ):
                allowed = True
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail="Complete company profile before using the workspace",
                )
    return user.id
'''


def patch_auth():
    t = AUTH.read_text(encoding="utf-8")
    t2, n = re.subn(
        r"def get_authenticated_user_id\([\s\S]*?return user\.id\n",
        NEW_GET_AUTH.lstrip("\n"),
        t,
        count=1,
    )
    if n != 1:
        raise SystemExit("get_authenticated_user_id not patched")
    AUTH.write_text(t2, encoding="utf-8")
    compile(AUTH.read_text(encoding="utf-8"), str(AUTH), "exec")
    print("[OK] auth.py onboarding allowlist for GET + profile + hire")


def patch_js_nan():
    if not JS.exists():
        return
    t = JS.read_text(encoding="utf-8")
    old = """      let dx = (e.clientX - cx) / (r.width / 2);
      let dy = (e.clientY - cy) / (r.height / 2);
      dx = Math.max(-1, Math.min(1, dx)) * 2.5;
      dy = Math.max(-1, Math.min(1, dy)) * 2;
      pupils.forEach((p) => {
        p.style.animation = "none";
        p.setAttribute("transform", `translate(${dx}, ${dy})`);
      });"""
    new = """      if (!r.width || !r.height) return;
      let dx = (e.clientX - cx) / (r.width / 2);
      let dy = (e.clientY - cy) / (r.height / 2);
      if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;
      dx = Math.max(-1, Math.min(1, dx)) * 2.5;
      dy = Math.max(-1, Math.min(1, dy)) * 2;
      pupils.forEach((p) => {
        p.style.animation = "none";
        p.setAttribute("transform", "translate(" + dx + ", " + dy + ")");
      });"""
    if old in t:
        t = t.replace(old, new, 1)
        print("[OK] pupil NaN guard")
    else:
        # softer replace
        t2, n = re.subn(
            r"let dx = \(e\.clientX - cx\) / \(r\.width / 2\);\s*"
            r"let dy = \(e\.clientY - cy\) / \(r\.height / 2\);\s*"
            r"dx = Math\.max\(-1, Math\.min\(1, dx\)\) \* 2\.5;\s*"
            r"dy = Math\.max\(-1, Math\.min\(1, dy\)\) \* 2;",
            "if (!r.width || !r.height) return;\n"
            "      let dx = (e.clientX - cx) / (r.width / 2);\n"
            "      let dy = (e.clientY - cy) / (r.height / 2);\n"
            "      if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;\n"
            "      dx = Math.max(-1, Math.min(1, dx)) * 2.5;\n"
            "      dy = Math.max(-1, Math.min(1, dy)) * 2;",
            t,
            count=1,
        )
        t = t2
        print("[OK] pupil NaN guard (regex)" if n else "[WARN] pupil block not found")
    JS.write_text(t, encoding="utf-8")


def main():
    print("Job 96 fix — onboarding 403 + pupil NaN")
    patch_auth()
    patch_js_nan()
    print(
        """
  Restart uvicorn + Ctrl+F5
  Login again — company/agents GET should work during onboarding
  Wizard should load without 403 noise.

  git add app/core/auth.py app/static/workspace/app.js
  git commit -m "Job 96 fix: allow onboarding API reads; guard pupil NaN"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
