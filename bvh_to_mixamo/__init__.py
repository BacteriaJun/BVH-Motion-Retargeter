import bpy
from bpy.app.handlers import persistent

from .addon_info import ADDON_NAME, ADDON_VERSION
from .core.i18n import language_changed, register_i18n, unregister_i18n
from .core.logger import log_info
from .core.template_loader import migrate_legacy_template_selection
from .operators import classes as operator_classes
from .properties import register_properties, unregister_properties
from .ui import classes as ui_classes

# Blender reads this literal before importing the add-on.
bl_info = {
    "name": "BVH Motion Retargeter",
    "author": "Junius",
    "version": (4, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > BVH Retarget",
    "description": (
        "A Blender add-on for converting BVH motion capture data to Mixamo, "
        "UE4/UE5 and VRM rigs, with editable VMD and bounded motion cleanup."
    ),
    "warning": "",
    "doc_url": "https://github.com/BacteriaJun/BVH-Motion-Retargeter",
    "category": "Animation",
}


classes = operator_classes + ui_classes
VERSION = '.'.join(str(part) for part in ADDON_VERSION)


def _initialize_project():
    # Preferences.addon_enable uses RestrictData until register() returns.
    scenes = getattr(bpy.data, "scenes", None)
    if scenes is None:
        return False
    migrate_legacy_template_selection(scene for scene in scenes if scene.library is None)
    language_changed(None, bpy.context)
    return True


@persistent
def _on_project_load(_unused):
    _initialize_project()


def _deferred_initialize():
    if not hasattr(bpy.types.Scene, "bvh_ui_language"):
        return None
    return None if _initialize_project() else 0.1


def register():
    register_properties()
    register_i18n()
    if not _initialize_project() and not bpy.app.timers.is_registered(_deferred_initialize):
        bpy.app.timers.register(_deferred_initialize, first_interval=0.0)
    if _on_project_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_project_load)
    for cls in classes:
        bpy.utils.register_class(cls)
    log_info(f'{ADDON_NAME} v{VERSION} registered | 3D View > N Sidebar > BVH Retarget')


def unregister():
    if bpy.app.timers.is_registered(_deferred_initialize):
        bpy.app.timers.unregister(_deferred_initialize)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    if _on_project_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_project_load)
    unregister_i18n()
    unregister_properties()
    log_info(f'{ADDON_NAME} v{VERSION} unregistered')


if __name__ == '__main__':
    register()
