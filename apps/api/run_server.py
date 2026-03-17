import argparse
import os

import uvicorn

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Retina local API server.")
    parser.add_argument("--host", default=os.getenv("RETINA_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("RETINA_API_PORT", "8000")))
    args = parser.parse_args()

    log_level = os.getenv("RETINA_API_LOG_LEVEL", "info")

    uvicorn.run(app, host=args.host, port=args.port, log_level=log_level, access_log=False)


if __name__ == "__main__":
    main()
