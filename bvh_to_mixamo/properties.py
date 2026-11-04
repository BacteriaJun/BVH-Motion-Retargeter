import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from .core.bone_mapping import MAPPING_PRESET_CUSTOM, MAPPING_PRESET_DEFAULT
from .core.export_profiles import EXPORT_PROFILE_AUTO, EXPORT_PROFILE_MIXAMO, EXPORT_PROFILE_UE4, EXPORT_PROFILE_UE5
from .core.retarget_engine import ROOT_IN_PLACE, ROOT_KEEP, ROOT_SCALE
from .core.template_loader import (
    TEMPLATE_PRESET_BUILTIN_BLACK,
    TEMPLATE_PRESET_BUILTIN_DEFAULT,
    TEMPLATE_PRESET_BUILTIN_GREEN,
    TEMPLATE_PRESET_BUILTIN_PINK,
    TEMPLATE_PRESET_BUILTIN_PURPLE,
    TEMPLATE_PRESET_BUILTIN_WHITE,
    TEMPLATE_PRESET_CUSTOM_FBX,
)
from .core.ue5_profile import (
    TARGET_MIXAMO,
    TARGET_UE4_BASIC,
    TARGET_UE5_BASIC,
    UE5_ROOT_BONE,
    UE5_ROOT_NONE,
    UE5_ROOT_PELVIS,
)
from .core.vrm_profile import TARGET_VRM_BODY


def register_properties():
    bpy.types.Scene.bvh_input_path = StringProperty(
        name="BVH Source File",
        default="",
        description="Select the source BVH motion capture file.",
        subtype="FILE_PATH",
    )
    bpy.types.Scene.bvh_match_fps = BoolProperty(
        name="Match BVH Frame Rate",
        default=True,
        description="Read the BVH frame time and apply the matching frame rate to the Blender scene.",
    )
    bpy.types.Scene.bvh_bind_mode = EnumProperty(
        name="Binding Mode",
        description="Choose how the converted motion will be applied.",
        items=[
            (
                "CREATE",
                "Create Target Armature",
                "Create a new target-format armature in the current scene.",
                "ARMATURE_DATA",
                0,
            ),
            (
                "BIND_SELECTED",
                "Bind to Selected Armature",
                "Retarget the BVH motion to the selected target armature.",
                "LINKED",
                1,
            ),
            (
                "BIND_TEMPLATE",
                "Bind to Character Template",
                "Import a built-in or custom character template and retarget the BVH motion to it.",
                "OUTLINER_OB_ARMATURE",
                2,
            ),
        ],
        default="CREATE",
    )
    bpy.types.Scene.bvh_target_skeleton = EnumProperty(
        name="Target Rig Profile",
        description="Choose the final target rig naming convention and structure.",
        items=[
            (TARGET_MIXAMO, "Mixamo Standard", "Use the standard mixamorig:* Mixamo bone naming.", "ARMATURE_DATA", 0),
            (
                TARGET_UE4_BASIC,
                "Unreal Engine 4 Humanoid",
                "UE-style three-spine humanoid for UE4 retargeting; not the Epic mannequin asset.",
                "OUTLINER_OB_ARMATURE",
                3,
            ),
            (
                TARGET_UE5_BASIC,
                "Unreal Engine 5 Humanoid",
                "Convert to UE-style root/pelvis/spine_01 naming with optional IK/twist helper bones.",
                "OUTLINER_OB_ARMATURE",
                1,
            ),
            (
                TARGET_VRM_BODY,
                "VRM Humanoid Body",
                "Retarget to VRM J_Bip body bones while ignoring J_Sec secondary hair, skirt, sleeve, and accessory bones.",
                "ARMATURE_DATA",
                2,
            ),
        ],
        default=TARGET_MIXAMO,
    )
    bpy.types.Scene.bvh_mapping_preset = EnumProperty(
        name="Source Mapping",
        description="Choose the source BVH to internal Mixamo mapping configuration.",
        items=[
            (
                MAPPING_PRESET_DEFAULT,
                "Built-in Default Mapping",
                "Use presets/default_mixamo_mapping.json.",
                "PRESET",
                0,
            ),
            (
                MAPPING_PRESET_CUSTOM,
                "Custom Mapping JSON",
                "Use a custom BVH-to-Mixamo bone mapping JSON file.",
                "FILE",
                1,
            ),
        ],
        default=MAPPING_PRESET_DEFAULT,
    )
    bpy.types.Scene.bvh_custom_mapping_path = StringProperty(
        name="Custom Mapping JSON",
        default="",
        description="Select a custom BVH-to-Mixamo intermediate mapping JSON file.",
        subtype="FILE_PATH",
    )
    bpy.types.Scene.bvh_template_preset = EnumProperty(
        name="Character Template",
        description="Choose the character template used by the template-binding workflow.",
        items=[
            (
                TEMPLATE_PRESET_BUILTIN_DEFAULT,
                "Default Character",
                "Built-in standard Mixamo-compatible character template.",
                "PRESET",
                0,
            ),
            (
                TEMPLATE_PRESET_BUILTIN_WHITE,
                "Default White",
                "Built-in character template with a white material variant.",
                "MATERIAL",
                1,
            ),
            (
                TEMPLATE_PRESET_BUILTIN_PINK,
                "Default Pink",
                "Built-in character template with a pink material variant.",
                "MATERIAL",
                2,
            ),
            (
                TEMPLATE_PRESET_BUILTIN_PURPLE,
                "Default Purple",
                "Built-in character template with a purple material variant.",
                "MATERIAL",
                3,
            ),
            (
                TEMPLATE_PRESET_BUILTIN_BLACK,
                "Default Black",
                "Built-in character template with a black material variant.",
                "MATERIAL",
                4,
            ),
            (
                TEMPLATE_PRESET_BUILTIN_GREEN,
                "Default Green",
                "Built-in character template with a green material variant.",
                "MATERIAL",
                5,
            ),
            (
                TEMPLATE_PRESET_CUSTOM_FBX,
                "Custom FBX / VRM",
                "Use a user-selected FBX, VRM, GLB, or GLTF character template.",
                "FILE",
                6,
            ),
        ],
        default=TEMPLATE_PRESET_BUILTIN_DEFAULT,
    )
    bpy.types.Scene.bvh_custom_template_fbx_path = StringProperty(
        name="Custom Character File",
        default="",
        description="Select a custom FBX, VRM, GLB, or GLTF character file.",
        subtype="FILE_PATH",
    )
    bpy.types.Scene.bvh_root_motion_mode = EnumProperty(
        name="Root Motion Handling",
        description="Control how root/hips translation is transferred during retargeting.",
        items=[
            (ROOT_KEEP, "Keep Source Motion", "Keep the original BVH hips translation.", "EMPTY_ARROWS", 0),
            (
                ROOT_IN_PLACE,
                "In-place Animation",
                "Reduce horizontal root motion for loopable game animation.",
                "ORIENTATION_LOCAL",
                1,
            ),
            (
                ROOT_SCALE,
                "Scale by Leg Length",
                "Scale root translation using the source/target leg-length ratio.",
                "FULLSCREEN_ENTER",
                2,
            ),
        ],
        default=ROOT_SCALE,
    )
    bpy.types.Scene.bvh_ue5_root_motion = EnumProperty(
        name="UE5 Root Motion",
        description="Control root/pelvis translation when converting to the UE5 humanoid profile.",
        items=[
            (UE5_ROOT_NONE, "No Root Motion", "新增root骨骼但不写入root位移，默认最稳定", "ORIENTATION_GLOBAL", 0),
            (
                UE5_ROOT_BONE,
                "Root Bone Motion",
                "将pelvis水平位移拆到root骨骼，适合UE Root Motion测试",
                "EMPTY_ARROWS",
                1,
            ),
            (UE5_ROOT_PELVIS, "Pelvis Only", "保留pelvis位移，不拆分到root", "ARMATURE_DATA", 2),
        ],
        default=UE5_ROOT_NONE,
    )

    bpy.types.Scene.bvh_ue5_add_auxiliary_bones = BoolProperty(
        name="Create UE5 Helper Bones",
        default=True,
        description="Generate Manny-style IK bones and lightweight twist helper bones. Helper bones are non-deforming by default.",
    )

    bpy.types.Scene.bvh_vrm_leg_roll_180 = BoolProperty(
        name="VRM Leg Axis Correction",
        default=True,
        description="Correct VRM thigh front/back local-axis orientation and use knee compensation while preserving the calf and foot chain.",
    )

    bpy.types.Scene.bvh_vrm_knee_compensation_left = FloatProperty(
        name="Left Knee Compensation",
        default=-45.0,
        min=-180.0,
        max=180.0,
        description="Fine-tune only the left lower-leg roll to reduce knee seam twisting. Foot and toe bones are preserved.",
    )

    bpy.types.Scene.bvh_vrm_knee_compensation_right = FloatProperty(
        name="Right Knee Compensation",
        default=45.0,
        min=-180.0,
        max=180.0,
        description="Fine-tune only the right lower-leg roll. Foot and toe bones are preserved.",
    )

    bpy.types.Scene.bvh_export_profile = EnumProperty(
        name="FBX Export Preset",
        description="Choose the FBX export preset. Auto selects Mixamo or UE5 according to the target rig profile.",
        items=[
            (
                EXPORT_PROFILE_AUTO,
                "Auto",
                "Automatically select the export preset from the target rig profile.",
                "AUTO",
                0,
            ),
            (EXPORT_PROFILE_MIXAMO, "Mixamo FBX", "Use the Mixamo/general FBX export preset.", "ARMATURE_DATA", 1),
            (
                EXPORT_PROFILE_UE4,
                "UE4 FBX",
                "Unreal-oriented animation FBX; retarget to your actual UE4 Skeleton.",
                "EXPORT",
                3,
            ),
            (EXPORT_PROFILE_UE5, "UE5 FBX", "Use Unreal Engine 5 friendly FBX export settings.", "EXPORT", 2),
        ],
        default=EXPORT_PROFILE_AUTO,
    )

    bpy.types.Scene.bvh_export_path = StringProperty(
        name="FBX Output Path",
        default="",
        description="Select the FBX file path used by manual or automatic export.",
        subtype="FILE_PATH",
    )
    bpy.types.Scene.bvh_auto_export_after_convert = BoolProperty(
        name="Auto Export After Convert",
        default=False,
        description="Automatically export with the selected FBX preset after a successful conversion.",
    )
    bpy.types.Scene.bvh_export_include_mesh = BoolProperty(
        name="Include Mesh",
        default=True,
        description="Include meshes bound to the armature during FBX export. Disable for animation-only tests.",
    )
    bpy.types.Scene.bvh_last_output_armature = StringProperty(
        name="Last Output Armature",
        default="",
        description="Name of the most recent armature generated or bound by the add-on.",
    )

    bpy.types.Scene.bvh_simplify_after_bake = BoolProperty(
        name="Simplify Curves After Bake",
        default=False,
        description="Reduce redundant F-curves created by per-frame BVH baking.",
    )
    bpy.types.Scene.bvh_simplify_factor = FloatProperty(
        name="Simplify Factor",
        default=0.01,
        min=0.0,
        max=1.0,
        description="F-curve simplification strength. Higher values produce stronger keyframe reduction.",
    )

    bpy.types.Scene.bvh_source_format = EnumProperty(
        name="Source Format",
        items=[("VMD", "VMD", "Import editable VMD motion."), ("BVH", "BVH", "Convert BVH motion.")],
        default="VMD",
    )
    bpy.types.Scene.bvh_vmd_input_path = StringProperty(name="VMD Source", subtype="FILE_PATH")
    bpy.types.Scene.bvh_vmd_output_path = StringProperty(name="VMD Output", subtype="FILE_PATH")
    bpy.types.Scene.bvh_vmd_import_mode = EnumProperty(
        name="Import To",
        items=[
            ("PREVIEW", "Reference Preview", "Create an explicit generic FK reference; VMD contains no rest skeleton."),
            (
                "SELECTED",
                "Selected MMD Rig",
                "Use Japanese bone names or mmd_bone.name_j on a compatible selected rig.",
            ),
        ],
        default="PREVIEW",
    )
    bpy.types.Scene.bvh_vmd_export_mode = EnumProperty(
        name="VMD Export",
        items=[
            ("PRESERVE", "Preserve Imported VMD", "Patch edited mapped bones, retaining all untouched sections."),
            (
                "NEW_FK",
                "New FK Motion",
                "Create explicit FK channels from a mapped rig; target rest and IK settings must match.",
            ),
        ],
        default="PRESERVE",
    )
    bpy.types.Scene.bvh_vmd_fk_mapping = EnumProperty(
        name="FK Mapping",
        items=[
            ("MIXAMO", "Mixamo", "Map mixamorig:* or source body bone names."),
            ("JAPANESE", "Japanese / MMD", "Use Japanese/VMD-labelled bone names."),
        ],
        default="MIXAMO",
    )
    bpy.types.Scene.bvh_vmd_finger_digits = EnumProperty(
        name="Target Finger Digits",
        items=[
            ("FULLWIDTH", "Full-width １/２/３", "Common MMD and supplied capture names."),
            ("ASCII", "ASCII 1/2/3", "Use only when these names match the target model."),
        ],
        default="FULLWIDTH",
    )
    bpy.types.Scene.bvh_vmd_unit_scale = FloatProperty(
        name="Blender Units per MMD Unit", default=0.08, min=0.000001, max=1000.0
    )
    bpy.types.Scene.bvh_vmd_reference_scale = BoolProperty(
        name="Estimate Scale from Reference Legs",
        default=True,
        description="For new FK output only: match source leg length to the generic reference. Calibrate to the actual MMD model for final use.",
    )
    bpy.types.Scene.bvh_vmd_frame_start = IntProperty(name="Import Start Frame", default=1, min=0)
    bpy.types.Scene.bvh_vmd_match_fps = BoolProperty(name="Use VMD 30 FPS", default=True)
    bpy.types.Scene.bvh_export_overwrite = BoolProperty(name="Overwrite Existing Output", default=False)
    bpy.types.Scene.bvh_export_allow_discontinuities = BoolProperty(
        name="Allow Large Root Discontinuities",
        default=False,
        description="Explicitly permit reviewed cuts/teleports in new exports; otherwise severe root steps block export.",
    )
    bpy.types.Scene.bvh_cleanup_window = FloatProperty(name="Filter Window (seconds)", default=0.12, min=0.03, max=0.5)
    bpy.types.Scene.bvh_cleanup_strength = FloatProperty(name="Denoise Strength", default=0.5, min=0.0, max=1.0)
    bpy.types.Scene.bvh_cleanup_cap = FloatProperty(
        name="Maximum Rotation Change (degrees)", default=3.0, min=0.1, max=15.0
    )
    bpy.types.Scene.bvh_cleanup_selected_bones = BoolProperty(name="Only Selected Pose Bones", default=False)
    bpy.types.Scene.bvh_gap_start = IntProperty(name="First Bad Frame", default=7, min=0)
    bpy.types.Scene.bvh_gap_end = IntProperty(name="Last Bad Frame", default=9, min=0)
    bpy.types.Scene.bvh_gap_root_bone = StringProperty(name="Root Bone (optional)")
    bpy.types.Scene.bvh_gap_video_confirmed = BoolProperty(
        name="Confirmed Capture Error in Source Video",
        default=False,
        description="Confirm these short samples are capture errors, with trusted samples on both sides. Actual jumps and camera cuts must not be reconstructed.",
    )


def unregister_properties():
    for prop in [
        "bvh_source_format",
        "bvh_vmd_input_path",
        "bvh_vmd_output_path",
        "bvh_vmd_import_mode",
        "bvh_vmd_export_mode",
        "bvh_vmd_fk_mapping",
        "bvh_vmd_finger_digits",
        "bvh_vmd_unit_scale",
        "bvh_vmd_reference_scale",
        "bvh_vmd_frame_start",
        "bvh_vmd_match_fps",
        "bvh_export_overwrite",
        "bvh_export_allow_discontinuities",
        "bvh_cleanup_window",
        "bvh_cleanup_strength",
        "bvh_cleanup_cap",
        "bvh_cleanup_selected_bones",
        "bvh_gap_start",
        "bvh_gap_end",
        "bvh_gap_root_bone",
        "bvh_gap_video_confirmed",
        "bvh_input_path",
        "bvh_match_fps",
        "bvh_bind_mode",
        "bvh_target_skeleton",
        "bvh_mapping_preset",
        "bvh_custom_mapping_path",
        "bvh_template_preset",
        "bvh_custom_template_fbx_path",
        "bvh_root_motion_mode",
        "bvh_ue5_root_motion",
        "bvh_ue5_add_auxiliary_bones",
        "bvh_vrm_leg_roll_180",
        "bvh_vrm_knee_compensation_left",
        "bvh_vrm_knee_compensation_right",
        "bvh_export_profile",
        "bvh_export_path",
        "bvh_auto_export_after_convert",
        "bvh_export_include_mesh",
        "bvh_last_output_armature",
        "bvh_simplify_after_bake",
        "bvh_simplify_factor",
    ]:
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
