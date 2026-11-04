import os

from bpy.types import Panel

from ..addon_info import ADDON_VERSION
from ..core.armature_utils import get_selected_mixamo_armature
from ..core.bone_mapping import MAPPING_PRESET_DEFAULT
from ..core.i18n import CONTEXT, TranslatedLayout
from ..core.paths import get_default_mapping_json_path, get_default_template_fbx_path
from ..core.template_loader import TEMPLATE_PRESET_CUSTOM_FBX, TEMPLATE_REGISTRY
from ..core.ue5_profile import TARGET_UE4_BASIC, TARGET_UE5_BASIC
from ..core.vrm_profile import TARGET_VRM_BODY


def draw_motion_cleanup(layout, scene):
    box = layout.box()
    box.label(text="Motion Review / Cleanup", icon="GRAPH")
    box.operator("bvh.audit_motion", text="Inspect Export Range", icon="VIEWZOOM")
    box.prop(scene, "bvh_cleanup_window")
    box.prop(scene, "bvh_cleanup_strength")
    box.prop(scene, "bvh_cleanup_cap")
    box.prop(scene, "bvh_cleanup_selected_bones")
    box.operator("bvh.cleanup_motion", text="Create Denoised Copy")
    box.label(text="Root travel and default finger tracks are retained.", icon="INFO")
    sub = box.box()
    sub.label(text="Short Capture Error (up to 150 ms)")
    row = sub.row(align=True)
    row.prop(scene, "bvh_gap_start")
    row.prop(scene, "bvh_gap_end")
    sub.prop(scene, "bvh_gap_root_bone")
    sub.prop(scene, "bvh_gap_video_confirmed")
    sub.operator("bvh.repair_root_gap", text="Create Root Repair Copy")
    sub.label(text="Needs trusted frames on both sides; no tail prediction.")


def draw_vmd_export(layout, scene):
    box = layout.box()
    box.label(text="VMD Export", icon="EXPORT")
    box.prop(scene, "bvh_vmd_export_mode")
    if scene.bvh_vmd_export_mode == "NEW_FK":
        box.prop(scene, "bvh_vmd_fk_mapping")
        if scene.bvh_vmd_fk_mapping == "MIXAMO":
            box.prop(scene, "bvh_vmd_finger_digits")
        box.prop(scene, "bvh_vmd_reference_scale")
        if not scene.bvh_vmd_reference_scale:
            box.prop(scene, "bvh_vmd_unit_scale")
        box.label(text="FK output: match the actual MMD model rest pose.", icon="INFO")
        box.label(text="Standard leg IK is disabled in new FK files.")
    row = box.row(align=True)
    row.prop(scene, "bvh_vmd_output_path", text="")
    row.operator("file.select_vmd_output", text="", icon="FILEBROWSER")
    box.prop(scene, "bvh_export_overwrite")
    box.operator("bvh.export_vmd", text="Export VMD", icon="EXPORT")


def draw_vmd_workflow(layout, scene):
    box = layout.box()
    box.label(text="1. VMD Source", icon="IMPORT")
    row = box.row(align=True)
    row.prop(scene, "bvh_vmd_input_path", text="")
    row.operator("file.select_vmd_input", text="", icon="FILEBROWSER")
    box.prop(scene, "bvh_vmd_import_mode")
    box.prop(scene, "bvh_vmd_unit_scale")
    box.prop(scene, "bvh_vmd_frame_start")
    box.prop(scene, "bvh_vmd_match_fps")
    box.operator("bvh.import_vmd", text="Import Editable VMD", icon="IMPORT")
    if scene.bvh_vmd_import_mode == "PREVIEW":
        box.label(text="Reference FK geometry; native MMD IK is not evaluated.", icon="INFO")
        box.label(text="Use a matching MMD rig for final model proportions.")
    draw_motion_cleanup(layout, scene)
    draw_vmd_export(layout, scene)


class MIXAMO_PT_panel(Panel):
    bl_idname = "MIXAMO_PT_main_panel"
    bl_label = "BVH Motion Retargeter"
    bl_translation_context = CONTEXT
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BVH Retarget"

    def draw_header(self, context):
        self.layout.label(icon="ARMATURE_DATA")

    def draw(self, context):
        layout = TranslatedLayout(self.layout, context)
        layout.scale_y = 1.05
        scene = context.scene
        layout.prop(scene, "bvh_ui_language", text="Language / 界面语言")
        layout.prop(scene, "bvh_source_format", expand=True)
        if scene.bvh_source_format == "VMD":
            draw_vmd_workflow(layout, scene)
            return

        box = layout.box()
        box.label(text="1. Source Motion", icon="IMPORT")
        row = box.row(align=True)
        row.prop(scene, "bvh_input_path", text="")
        row.operator("file.select_bvh", text="", icon="FILEBROWSER")
        box.prop(scene, "bvh_match_fps")

        box = layout.box()
        box.label(text="2. Source Mapping", icon="BONE_DATA")
        box.prop(scene, "bvh_mapping_preset", text="")
        if scene.bvh_mapping_preset == MAPPING_PRESET_DEFAULT:
            path = get_default_mapping_json_path()
            box.label(text="Using built-in default_mixamo_mapping.json", icon="CHECKMARK")
            if not os.path.exists(path):
                row = box.row()
                row.alert = True
                row.label(text="Built-in mapping file is missing; fallback mapping will be used.", icon="ERROR")
        else:
            row = box.row(align=True)
            row.prop(scene, "bvh_custom_mapping_path", text="")
            row.operator("file.select_mapping_json", text="", icon="FILEBROWSER")
            if not scene.bvh_custom_mapping_path:
                row = box.row()
                row.alert = True
                row.label(text="Select a custom mapping JSON file.", icon="ERROR")

        box = layout.box()
        box.label(text="3. Target Rig Profile", icon="OUTLINER_OB_ARMATURE")
        box.prop(scene, "bvh_target_skeleton", text="")
        if scene.bvh_target_skeleton in {TARGET_UE4_BASIC, TARGET_UE5_BASIC}:
            box.prop(scene, "bvh_ue5_root_motion", text="Root Motion")
            box.prop(scene, "bvh_ue5_add_auxiliary_bones")
            col = box.column(align=True)
            col.scale_y = 0.85
            col.label(text="UE profile: root → pelvis → spine_01", icon="INFO")
            col.label(text="Optional IK/twist helper bones are non-deforming.")
        elif scene.bvh_target_skeleton == TARGET_VRM_BODY:
            col = box.column(align=True)
            col.scale_y = 0.85
            col.label(text="VRM profile: Mixamo intermediate rig → J_Bip body bones", icon="INFO")
            col.label(text="J_Sec secondary hair/skirt/sleeve/accessory bones are ignored.")
            box.prop(scene, "bvh_vrm_leg_roll_180")
            if scene.bvh_vrm_leg_roll_180:
                row = box.row(align=True)
                row.prop(scene, "bvh_vrm_knee_compensation_left", text="Left Knee")
                row.prop(scene, "bvh_vrm_knee_compensation_right", text="Right Knee")

        box = layout.box()
        box.label(text="4. Binding Mode", icon="MODIFIER")
        box.prop(scene, "bvh_bind_mode", text="")
        if scene.bvh_bind_mode == "BIND_SELECTED":
            if scene.bvh_target_skeleton == TARGET_VRM_BODY:
                selected_armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
                selected = selected_armatures[0] if selected_armatures else None
                if selected:
                    box.label(text=box.t("Selected VRM armature: {name}", name=selected.name), icon="CHECKMARK")
                else:
                    row = box.row()
                    row.alert = True
                    row.label(text="Select the target VRM Armature first.", icon="ERROR")
            else:
                selected = get_selected_mixamo_armature()
                if selected:
                    box.label(text=box.t("Selected target: {name}", name=selected.name), icon="CHECKMARK")
                else:
                    row = box.row()
                    row.alert = True
                    row.label(text="Select a Mixamo-compatible target armature first.", icon="ERROR")
        if scene.bvh_bind_mode == "BIND_TEMPLATE":
            sub = box.box()
            sub.label(text="Character Template", icon="OUTLINER_OB_ARMATURE")
            sub.prop(scene, "bvh_template_preset", text="")
            if scene.bvh_template_preset != TEMPLATE_PRESET_CUSTOM_FBX:
                template_info = TEMPLATE_REGISTRY.get(scene.bvh_template_preset, {})
                filename = template_info.get("filename", "mixamo_default_white.fbx")
                path = os.path.join(os.path.dirname(get_default_template_fbx_path()), filename)
                sub.label(
                    text=sub.t("Built-in template: {name}", name=sub.t(template_info.get("name", "Default White"))),
                    icon="CHECKMARK",
                )
                if not os.path.exists(path):
                    row = sub.row()
                    row.alert = True
                    row.label(text="Built-in character template is missing.", icon="ERROR")
            else:
                row = sub.row(align=True)
                row.prop(scene, "bvh_custom_template_fbx_path", text="")
                row.operator("file.select_template_fbx", text="", icon="FILEBROWSER")

        box = layout.box()
        box.label(text="5. Retarget Settings", icon="CONSTRAINT_BONE")
        box.label(text="Solver: Constraint Bake retargeting", icon="CHECKMARK")
        box.prop(scene, "bvh_root_motion_mode", text="Root Motion")
        box.prop(scene, "bvh_simplify_after_bake")
        if scene.bvh_simplify_after_bake:
            box.prop(scene, "bvh_simplify_factor")

        box = layout.box()
        box.label(text="6. FBX Export", icon="EXPORT")
        box.prop(scene, "bvh_export_profile", text="Preset")
        row = box.row(align=True)
        row.prop(scene, "bvh_export_path", text="")
        row.operator("file.select_export_fbx", text="", icon="FILEBROWSER")
        box.prop(scene, "bvh_auto_export_after_convert")
        box.prop(scene, "bvh_export_include_mesh")
        box.prop(scene, "bvh_export_overwrite")
        box.prop(scene, "bvh_export_allow_discontinuities")
        if scene.bvh_last_output_armature:
            box.label(text=box.t("Last output: {name}", name=scene.bvh_last_output_armature), icon="CHECKMARK")
        row = box.row()
        row.scale_y = 1.35
        row.operator("mixamo.export_fbx", text="Export with Selected Preset", icon="EXPORT")
        row = box.row(align=True)
        row.operator("mixamo.export_mixamo_fbx", text="Export Mixamo FBX", icon="ARMATURE_DATA")
        row.operator("mixamo.export_ue5_fbx", text="Export UE5 FBX", icon="EXPORT")
        box.operator("mixamo.export_ue4_fbx", text="Export UE4 FBX", icon="EXPORT")
        draw_motion_cleanup(layout, scene)
        draw_vmd_export(layout, scene)

        layout.separator()
        row = layout.row()
        row.scale_y = 2.0
        if scene.bvh_bind_mode == "BIND_SELECTED":
            row.operator("mixamo.convert_bvh", text="Retarget to Selected Armature", icon="LINKED")
        elif scene.bvh_bind_mode == "BIND_TEMPLATE":
            row.operator("mixamo.convert_bvh", text="Retarget to Character Template", icon="OUTLINER_OB_ARMATURE")
        else:
            row.operator("mixamo.convert_bvh", text="Create Target Armature", icon="ARMATURE_DATA")

        box = layout.box()
        box.label(text=box.t("BVH Motion Retargeter {version}", version=".".join(map(str, ADDON_VERSION))), icon="INFO")
        col = box.column(align=True)
        col.scale_y = 0.85
        col.label(text="• Stable Constraint Bake retargeting pipeline")
        col.label(text="• VMD, Mixamo, UE4/UE5 and VRM Body workflows")
        col.label(text="• Black and white Mixamo characters")
        col.label(text="• Integrated Mixamo and UE4/UE5 FBX export presets")
        col.label(text="• VRM body-only mapping with knee compensation controls")
