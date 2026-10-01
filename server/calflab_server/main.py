"""Run the CALFLAB server."""

from __future__ import annotations

import logging
from pathlib import Path

from calflab.app import Lab

from calflab_server.app import create_app


def serve(
    project: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    web_dist: Path | None = None,
    log_level: str = "info",
) -> None:
    """Open (or create) the project and serve it until interrupted."""
    import uvicorn

    logging.basicConfig(level=log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    lab = Lab.open(project)
    app = create_app(lab, web_dist)
    try:
        uvicorn.run(app, host=host, port=port, log_level=log_level)
    finally:
        from calflab.compute.local import LocalProcessPool

        LocalProcessPool.shutdown_all()
        lab.close()


if __name__ == "__main__":  # python -m calflab_server.main <project>
    import sys

    serve(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("projects/sample-calf"))
