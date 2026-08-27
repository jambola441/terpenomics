"""Configuration for the Metrc API proficiency evaluation runner.

Everything is driven by environment variables so no key ever lands in the repo.
See .env.example for the full list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    pass


def _host(state: str, sandbox: bool) -> str:
    prefix = "sandbox-api" if sandbox else "api"
    return f"https://{prefix}-{state.lower()}.metrc.com"


@dataclass
class MetrcConfig:
    state: str = "ny"
    sandbox: bool = True
    vendor_key: str = ""
    user_key: str = ""
    license_number: str = ""
    # Where recorded call transcripts land.
    run_dir: str = "evidence/metrc"
    # Seconds to wait when the API asks us to back off and gives no Retry-After.
    default_backoff: float = 30.0
    max_retries: int = 4
    timeout: float = 60.0
    extra: dict = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return _host(self.state, self.sandbox)

    @property
    def docs_url(self) -> str:
        return f"{_host(self.state, False)}/Documentation/"

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n, "")]
        if missing:
            raise ConfigError(
                "missing required config: "
                + ", ".join(f"METRC_{n.upper()}" for n in missing)
            )

    @classmethod
    def from_env(cls) -> "MetrcConfig":
        sandbox = os.getenv("METRC_SANDBOX", "true").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        return cls(
            state=os.getenv("METRC_STATE", "ny").strip(),
            sandbox=sandbox,
            vendor_key=os.getenv("METRC_VENDOR_KEY", "").strip(),
            user_key=os.getenv("METRC_USER_KEY", "").strip(),
            license_number=os.getenv("METRC_LICENSE_NUMBER", "").strip(),
            run_dir=os.getenv("METRC_RUN_DIR", "evidence/metrc").strip(),
        )
