import os
import sys
import pathlib
import argparse
import multiprocessing

from musix import settings
from musix.logger import setup_logger
from musix import tools as musix_tools
from musix.settings import AssetHandler, Metadata
from musix.start_musix import start_musix

parser = argparse.ArgumentParser(
    prog="musix",
    description="Awesome Music",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)

parser.add_argument(
    "-v", "--version", action="version", version=f"musix v{Metadata.version}"
)
parser.add_argument("--host", default="0.0.0.0", help="Host to run the app on.")
parser.add_argument(
    "--port",
    default=int(os.environ.get("MUSIX_PORT") or 1970),
    help="HTTP port to run the app on. Falls back to $MUSIX_PORT, then 1970.",
    type=int,
)
parser.add_argument(
    "--debug",
    default=False,
    action="store_true",
    help="If musix should start in debug mode",
)
parser.add_argument(
    "--config",
    default=settings.Paths.get_default_config_parent_dir(),
    help="The directory to setup the config folder.",
    type=pathlib.Path,
)
parser.add_argument("--client", help="Path to the Web UI folder.", type=pathlib.Path)

tools = parser.add_argument_group(title="Tools")
tools.add_argument("--password-reset", help="Reset the password.", action="store_true")


def run(*args, **kwargs):
    """
    MUSIX entry point
    """
    args = parser.parse_args()
    args = vars(args)

    config_parent = args["config"]
    client_path = args["client"]

    # INFO: Validate client path
    if client_path is not None:
        client_path = pathlib.Path(client_path).resolve()

        if not client_path.exists():
            print(
                f"Client path {client_path} does not exist. Please provide a valid path"
            )
            sys.exit(1)
        else:
            # INFO: check if client path has index.html
            if not (client_path / "index.html").exists():
                print(
                    f"Client path {client_path} does not contain an index.html file. Please provide a valid path"
                )
                sys.exit(1)

    settings.Paths(config_parent=config_parent, client_dir=client_path)

    AssetHandler.copy_assets_dir()
    AssetHandler.setup_default_client()

    os.environ["MUSIX_DEBUG"] = "1" if args["debug"] else "0"
    setup_logger(debug=args["debug"], app_dir=settings.Paths().config_dir)

    if args["password_reset"]:
        musix_tools.handle_password_reset(config_parent)
        sys.exit(0)

    # start musix
    start_musix(host=args["host"], port=args["port"])


if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn")
    run()
