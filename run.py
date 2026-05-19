"""Entry point for STAN — run with: python run.py"""

import uvicorn

from stan.config import HOST, PORT


def main() -> None:
    uvicorn.run(
        "stan.api.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
