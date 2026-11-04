import os

DEFAULT_MAPPING_JSON_FILENAME = "default_mixamo_mapping.json"
DEFAULT_TEMPLATE_FBX_FILENAME = "mixamo_default_white.fbx"


def get_addon_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_presets_dir():
    return os.path.join(get_addon_dir(), "presets")


def get_templates_dir():
    return os.path.join(get_addon_dir(), "templates")


def get_docs_dir():
    return os.path.join(get_addon_dir(), "docs")


def get_default_mapping_json_path():
    return os.path.join(get_presets_dir(), DEFAULT_MAPPING_JSON_FILENAME)


def get_default_template_fbx_path():
    return os.path.join(get_templates_dir(), DEFAULT_TEMPLATE_FBX_FILENAME)
