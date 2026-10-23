import os
from pathlib import Path, PurePosixPath

from musix.settings import Paths
from musix.config import UserConfig


def is_path_within_root_dirs(filepath: str) -> bool:
    """
    Check if a filepath is within one of the configured root directories.
    Prevents directory traversal attacks.
    """
    config = UserConfig()
    resolved_path = Path(filepath).resolve()

    for root_dir in config.rootDirs:
        if root_dir == "$home":
            root_path = Path.home().resolve()
        else:
            root_path = Path(root_dir).resolve()

        # Check if resolved_path is the root or a child of root
        if resolved_path == root_path or root_path in resolved_path.parents:
            return True

    return False


def host_path_pairs() -> list[tuple[PurePosixPath, PurePosixPath]]:
    """
    The pairs of `MUSIX_HOST_PATHS` (`/music=/HD_1_TB/Músicas;/other=/HD_1_TB/Other`):
    the folder as the container sees it, and the same folder as the file manager of the host shows it.
    """
    pairs = []

    for pair in os.environ.get("MUSIX_HOST_PATHS", "").split(";"):
        container, sep, host = pair.partition("=")
        container, host = container.strip(), host.strip()

        if sep and container and host:
            pairs.append((PurePosixPath(container), PurePosixPath(host)))

    return pairs


def to_host_path(path: str) -> str | None:
    """
    Turns a path of the container into the path of the same folder on the host (see
    `MUSIX_HOST_PATHS`). The first pair that holds the path wins, compared by path parts, not by
    text (`/music2` is not inside `/music`). None when there is no configuration or no pair holds it.
    """
    parts = PurePosixPath(path.replace("\\", "/")).parts

    for container, host in host_path_pairs():
        prefix = container.parts

        if parts[: len(prefix)] == prefix:
            return PurePosixPath(host, *parts[len(prefix) :]).as_posix()

    return None


def files_url_template() -> str | None:
    """
    The address of the file manager of the host, from `MUSIX_FILES_URL`: `{origin}` is where the
    user opened the app (the client fills it) and `{path}` the folder (see `to_host_path`).
    """
    return os.environ.get("MUSIX_FILES_URL", "").strip() or None


def get_client_files_extensions():
    """
    Get all the file extensions for the client files
    """

    extensions = set()
    for root, dirs, files in os.walk(Paths().client_path):
        for file in files:
            ext = file.split(".")[-1]
            extensions.add("." + ext)

    return extensions


def normalize_paths(paths: list[str]) -> list[str]:
    """
    Given a list of paths, returns a list of paths where no path is a child of another path
    """
    if not paths:
        return []

    # Convert to absolute paths for proper comparison
    abs_paths = [Path(path).resolve() for path in paths]

    # Sort paths by length (shorter paths first) to check parents before children
    sorted_paths = sorted(abs_paths, key=lambda p: len(p.parts))

    normalized = []

    for current_path in sorted_paths:
        # Check if current_path is a child of any path already in normalized list
        is_child = False
        for existing_path in normalized:
            try:
                # Check if current_path is relative to existing_path
                current_path.relative_to(existing_path)
                is_child = True
                break
            except ValueError:
                # current_path is not relative to existing_path, continue checking
                continue

        # Only add if it's not a child of any existing path
        if not is_child:
            normalized.append(current_path.as_posix())

    return normalized
