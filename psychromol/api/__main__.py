
from __future__ import annotations

import uvicorn

from ..config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"PsychroMol → http://{settings.host}:{settings.port}")
    print(f"API documentation → http://{settings.host}:{settings.port}/api/docs")
    uvicorn.run(
        "psychromol.api.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )

if __name__ == "__main__":
    main()
