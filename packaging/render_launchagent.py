"""Render the LaunchAgent without shell expansion or unresolved placeholders."""
import os
import plistlib
import re
from pathlib import Path


def render(value, replacements):
    if isinstance(value, dict):
        return {key: render(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, replacements) for item in value]
    if isinstance(value, str):
        value = re.sub(r"__WAX_AND_WANE_[A-Z_]+__", lambda match: replacements[match.group()], value)
    return value


def main():
    replacements = {
        "__WAX_AND_WANE_BINARY__": os.environ["WAX_BINARY"],
        "__WAX_AND_WANE_CONFIG__": os.environ["WAX_CONFIG"],
        "__WAX_AND_WANE_LOG_DIR__": os.environ["WAX_LOG_DIR"],
    }
    if not all(Path(value).is_absolute() for value in replacements.values()):
        raise ValueError("LaunchAgent paths must be absolute")
    with open(os.environ["WAX_TEMPLATE"], "rb") as source:
        result = render(plistlib.load(source), replacements)
    with open(os.environ["WAX_OUTPUT"], "wb") as destination:
        plistlib.dump(result, destination, fmt=plistlib.FMT_XML, sort_keys=False)


if __name__ == "__main__":
    main()
