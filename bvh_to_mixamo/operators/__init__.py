from .convert import MIXAMO_OT_convert
from .export_fbx import (
    MIXAMO_OT_export_fbx,
    MIXAMO_OT_export_mixamo_fbx,
    MIXAMO_OT_export_ue4_fbx,
    MIXAMO_OT_export_ue5_fbx,
)
from .file_selectors import (
    FILE_OT_select_bvh,
    FILE_OT_select_export_fbx,
    FILE_OT_select_mapping_json,
    FILE_OT_select_template_fbx,
)
from .motion_cleanup import BVH_OT_audit_motion, BVH_OT_cleanup_motion, BVH_OT_repair_root_gap
from .vmd_io import BVH_OT_export_vmd, BVH_OT_import_vmd, FILE_OT_select_vmd_input, FILE_OT_select_vmd_output

classes = (
    BVH_OT_import_vmd,
    BVH_OT_export_vmd,
    FILE_OT_select_vmd_input,
    FILE_OT_select_vmd_output,
    BVH_OT_audit_motion,
    BVH_OT_cleanup_motion,
    BVH_OT_repair_root_gap,
    MIXAMO_OT_export_ue4_fbx,
    MIXAMO_OT_convert,
    MIXAMO_OT_export_fbx,
    MIXAMO_OT_export_mixamo_fbx,
    MIXAMO_OT_export_ue5_fbx,
    FILE_OT_select_bvh,
    FILE_OT_select_mapping_json,
    FILE_OT_select_template_fbx,
    FILE_OT_select_export_fbx,
)
