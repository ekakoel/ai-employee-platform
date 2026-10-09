#!/usr/bin/env python3
"""Fix user_to_read ValidationError: User.role is ORM object, UserRead.role is str."""
from pathlib import Path

p = Path("app/api/routes.py")
t = p.read_text(encoding="utf-8")
old = '''def user_to_read(user: User) -> UserRead:
    """Serialize User with resolved role name for UI."""
    data = UserRead.model_validate(user)
    role_name = user.role.name if user.role is not None else None
    return data.model_copy(update={"role": role_name})
'''
new = '''def user_to_read(user: User) -> UserRead:
    """Serialize User with role name string (not the Role ORM relationship)."""
    role_obj = getattr(user, "role", None)
    role_name = role_obj.name if role_obj is not None else None
    return UserRead(
        id=user.id,
        company_id=user.company_id,
        name=user.name,
        email=user.email,
        role_id=user.role_id,
        role=role_name,
        department_id=getattr(user, "department_id", None),
        status=user.status,
        is_platform_admin=bool(getattr(user, "is_platform_admin", False)),
        created_at=user.created_at,
    )
'''
if old not in t:
    # broader match
    import re
    m = re.search(
        r"def user_to_read\(user: User\) -> UserRead:.*?return data\.model_copy\(update=\{\"role\": role_name\}\)\n",
        t,
        re.S,
    )
    if not m:
        if "role_obj = getattr(user" in t:
            print("already fixed")
            raise SystemExit(0)
        raise SystemExit("user_to_read block not found — paste fix manually")
    t = t[: m.start()] + new + t[m.end() :]
else:
    t = t.replace(old, new)
p.write_text(t, encoding="utf-8")
print("fixed app/api/routes.py user_to_read")
