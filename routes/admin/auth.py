import os
from fastapi import Depends, HTTPException, status

from auth import SupabaseAuthUser, get_current_user


def require_admin(user: SupabaseAuthUser = Depends(get_current_user)) -> SupabaseAuthUser:
    """
    MVP admin check:
    - expects Supabase JWT claim `role` == "admin"
    How to set:
    - easiest is Supabase custom claims / RLS policy approach later
    - for MVP, you can use a single admin user and manually set the claim,
      or replace this with an allowlist of admin user_ids in env.
    """
    # Option A: claim-based
    if user.role == "admin":
        return user

    # Option B: allowlist fallback
    allowlist = {
        x.strip() for x in (os.getenv("ADMIN_USER_IDS", "")).split(",") if x.strip()
    }
    if allowlist and user.user_id in allowlist:
        return user

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
