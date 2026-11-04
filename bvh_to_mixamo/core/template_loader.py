import os
import shutil
import tempfile

import bpy

from .armature_utils import find_mixamo_armature_in_objects, is_mixamo_armature
from .logger import log_info, log_warning
from .paths import get_default_template_fbx_path, get_templates_dir
from .vrm_profile import is_vrm_body_armature

TEMPLATE_PRESET_BUILTIN_DEFAULT = "BUILTIN_DEFAULT_CHARACTER"
TEMPLATE_PRESET_BUILTIN_WHITE = "BUILTIN_WHITE_CHARACTER"
TEMPLATE_PRESET_BUILTIN_PINK = "BUILTIN_PINK_CHARACTER"
TEMPLATE_PRESET_BUILTIN_PURPLE = "BUILTIN_PURPLE_CHARACTER"
TEMPLATE_PRESET_BUILTIN_BLACK = "BUILTIN_BLACK_CHARACTER"
TEMPLATE_PRESET_BUILTIN_GREEN = "BUILTIN_GREEN_CHARACTER"
TEMPLATE_PRESET_CUSTOM_FBX = "CUSTOM_FBX"

TEMPLATE_REGISTRY = {
    TEMPLATE_PRESET_BUILTIN_WHITE: {
        "name": "White Character",
        "filename": "mixamo_default_white.fbx",
        "format": "FBX",
        "description": "Built-in white Mixamo character",
    },
    TEMPLATE_PRESET_BUILTIN_BLACK: {
        "name": "Black Character",
        "filename": "mixamo_default_black.fbx",
        "format": "FBX",
        "description": "Built-in black Mixamo character",
    },
}
# Older .blend presets resolve to White without retaining duplicate model files.
RETIRED_TEMPLATE_PRESETS = frozenset(
    {
        TEMPLATE_PRESET_BUILTIN_DEFAULT,
        TEMPLATE_PRESET_BUILTIN_PINK,
        TEMPLATE_PRESET_BUILTIN_PURPLE,
        TEMPLATE_PRESET_BUILTIN_GREEN,
    }
)


def migrate_legacy_template_selection(scenes):
    """Map retired saved presets to White; retain Black, White and Custom.

    Enum properties are stored as numeric IDs in .blend files. Explicit string
    ID properties from older scripts are accepted as well. Character paths are
    deliberately outside this migration.
    """
    changed = []
    numeric = {
        0: TEMPLATE_PRESET_BUILTIN_WHITE,
        1: TEMPLATE_PRESET_BUILTIN_WHITE,
        2: TEMPLATE_PRESET_BUILTIN_WHITE,
        3: TEMPLATE_PRESET_BUILTIN_WHITE,
        4: TEMPLATE_PRESET_BUILTIN_BLACK,
        5: TEMPLATE_PRESET_BUILTIN_WHITE,
        6: TEMPLATE_PRESET_CUSTOM_FBX,
    }
    current = {TEMPLATE_PRESET_BUILTIN_WHITE: 1, TEMPLATE_PRESET_BUILTIN_BLACK: 4, TEMPLATE_PRESET_CUSTOM_FBX: 6}
    for scene in scenes:
        raw = scene.get("bvh_template_preset")
        target = None
        if type(raw) is int:
            target = numeric.get(raw)
        elif isinstance(raw, str):
            if raw in RETIRED_TEMPLATE_PRESETS:
                target = TEMPLATE_PRESET_BUILTIN_WHITE
            elif raw in current:
                target = raw
        elif raw is None:
            # Newer Blender versions keep registered RNA storage separately.
            # A removed numeric value reads as an empty enum identifier there.
            selected = getattr(scene, "bvh_template_preset", None)
            if selected == "" or selected in RETIRED_TEMPLATE_PRESETS:
                target = TEMPLATE_PRESET_BUILTIN_WHITE
        if target is not None:
            # Clear the legacy ID key before writing through RNA. In Blender
            # versions with separate stores, retaining that key would override
            # a later user selection when this migration runs again.
            if "bvh_template_preset" in scene:
                del scene["bvh_template_preset"]
            scene.bvh_template_preset = target
            if raw is None or type(raw) is str or raw in {0, 2, 3, 5}:
                changed.append(scene.name)
    return {"changed_scene_count": len(changed), "changed_scenes": changed}


def get_template_fbx_path(context):
    preset = getattr(context.scene, "bvh_template_preset", TEMPLATE_PRESET_BUILTIN_WHITE)
    if preset == TEMPLATE_PRESET_CUSTOM_FBX:
        path = getattr(context.scene, "bvh_custom_template_fbx_path", "")
        if not path:
            raise FileNotFoundError("Please select a custom FBX/VRM character file.")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Custom character file does not exist: {path}")
        if not path.lower().endswith((".fbx", ".vrm", ".glb", ".gltf")):
            raise ValueError("Custom character template must be a .fbx, .vrm, .glb, or .gltf file.")
        return path
    template_info = TEMPLATE_REGISTRY.get(preset) or TEMPLATE_REGISTRY[TEMPLATE_PRESET_BUILTIN_WHITE]
    filename = template_info.get("filename", "mixamo_default_white.fbx")
    if template_info is TEMPLATE_REGISTRY[TEMPLATE_PRESET_BUILTIN_WHITE]:
        path = get_default_template_fbx_path()
    else:
        path = os.path.join(get_templates_dir(), filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Built-in character template is missing: {path}")
    return path


def _import_vrm_or_gltf(filepath):
    """Import VRM through Blender's glTF importer.

    Blender's native glTF importer can usually read VRM because VRM is based on
    binary glTF. If the .vrm extension is rejected by a local Blender build, this
    function retries with a temporary .glb copy.
    """
    try:
        bpy.ops.import_scene.gltf(filepath=filepath)
        return
    except Exception as first_exc:
        if not filepath.lower().endswith(".vrm"):
            raise
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".glb")
            tmp.close()
            shutil.copyfile(filepath, tmp.name)
            bpy.ops.import_scene.gltf(filepath=tmp.name)
            log_warning(f"直接导入VRM失败，已用临时GLB路径重试: {first_exc}")
        finally:
            if tmp and os.path.exists(tmp.name):
                try:
                    os.remove(tmp.name)
                except Exception:
                    pass


def import_character_template_fbx(template_path):
    if not template_path or not os.path.exists(template_path):
        raise FileNotFoundError(f"Character template does not exist: {template_path}")
    before = set(bpy.data.objects)
    log_info(f"Importing character template: {template_path}")
    lower = template_path.lower()
    if lower.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=template_path)
    elif lower.endswith((".vrm", ".glb", ".gltf")):
        _import_vrm_or_gltf(template_path)
    else:
        raise ValueError("Unsupported character template format. Use FBX, VRM, GLB, or GLTF.")

    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not imported:
        raise RuntimeError("No imported objects were detected after importing the character template.")

    armatures = [obj for obj in imported if obj and obj.type == "ARMATURE"]
    armature = None
    for candidate in armatures:
        if is_vrm_body_armature(candidate):
            armature = candidate
            break
    if not armature:
        armature = find_mixamo_armature_in_objects(imported) or find_mixamo_armature_in_objects(
            bpy.context.selected_objects
        )
    if not armature:
        raise RuntimeError("No armature object was found in the character template.")

    if not (is_mixamo_armature(armature) or is_vrm_body_armature(armature)):
        log_warning(
            "The template armature is not a typical Mixamo or VRM J_Bip rig; the add-on will still attempt to use it as the target."
        )
    if armature.animation_data and armature.animation_data.action:
        armature.animation_data.action = None
    base_name = os.path.splitext(os.path.basename(template_path))[0]
    armature.name = f"{base_name}_AnimatedRig"
    armature.data.name = f"{base_name}_AnimatedRigData"
    for obj in imported:
        obj.select_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    log_info(
        f"Character template import completed. Target armature: {armature.name}，Imported object count: {len(imported)}"
    )
    return armature, imported
