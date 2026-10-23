#!/usr/bin/env python3
"""Allow 6-digit OTP on /auth/verify-email (was min_length=20)."""
from pathlib import Path

path = Path("app/api/auth_routes.py")
t = path.read_text(encoding="utf-8")
old = '''class VerificationRequest(BaseModel):
    token: str = Field(min_length=20)'''
new = '''class VerificationRequest(BaseModel):
    # Job 95: 6-digit OTP (also accepts legacy longer tokens)
    token: str = Field(min_length=6, max_length=128)'''
if old not in t:
    # flexible
    import re
    t2, n = re.subn(
        r"class VerificationRequest\(BaseModel\):\n\s*token: str = Field\(min_length=\d+\)",
        "class VerificationRequest(BaseModel):\n"
        "    token: str = Field(min_length=6, max_length=128)  # Job 95 OTP",
        t,
        count=1,
    )
    if n != 1:
        raise SystemExit("VerificationRequest not found")
    t = t2
else:
    t = t.replace(old, new, 1)
path.write_text(t, encoding="utf-8")
compile(path.read_text(encoding="utf-8"), str(path), "exec")
print("[OK] VerificationRequest min_length=6")
print("Restart uvicorn, then Activate again with 6-digit code.")
print('git add app/api/auth_routes.py && git commit -m "fix: accept 6-digit OTP on verify-email" && git push origin development')
