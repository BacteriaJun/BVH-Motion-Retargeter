ADDON_NAME = "BVH Motion Retargeter"
ADDON_AUTHOR = "Junius"
ADDON_VERSION = (4, 0, 0)
ADDON_BLENDER_VERSION = (4, 2, 0)
ADDON_CATEGORY = "Animation"
ADDON_LOCATION = "3D View > Sidebar > BVH Retarget"
ADDON_DESCRIPTION = (
    "A Blender add-on for converting BVH motion capture data to Mixamo, "
    "UE4/UE5 and VRM rigs, with editable VMD and bounded motion cleanup."
)
ADDON_DOC_URL = "https://github.com/BacteriaJun/BVH-Motion-Retargeter"

bl_info = {
    "name": ADDON_NAME,
    "author": ADDON_AUTHOR,
    "version": ADDON_VERSION,
    "blender": ADDON_BLENDER_VERSION,
    "location": ADDON_LOCATION,
    "description": ADDON_DESCRIPTION,
    "warning": "4.0.0 RC1: local pre-release validation build",
    "doc_url": ADDON_DOC_URL,
    "category": ADDON_CATEGORY,
}
