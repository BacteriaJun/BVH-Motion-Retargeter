"""Per-add-on English/Chinese UI, without changing Blender preferences.

Enum strings are held for the life of this module: Blender keeps references to
Python callback item strings. Only display text is translated; identifiers,
paths, bone names and animation values are never rewritten.
"""

from __future__ import annotations

import re
import string

try:
    import bpy
except ModuleNotFoundError:  # Pure catalog/format tests do not require Blender.
    bpy = None

try:
    from .i18n_errors import ERROR_TRANSLATIONS
except ImportError:
    ERROR_TRANSLATIONS = {}

CONTEXT = "BVH_MOTION_RETARGETER"
DOMAIN = "bvh_to_mixamo.interface"

TRANSLATIONS = {
    "Language / 界面语言": "Language / 界面语言",
    "Choose the language for this add-on only.": "仅切换本插件的界面语言。",
    "1. Source Motion": "1. 源动作",
    "1. VMD Source": "1. VMD 源动作",
    "2. Source Mapping": "2. 源骨骼映射",
    "3. Target Rig Profile": "3. 目标骨架",
    "4. Binding Mode": "4. 绑定方式",
    "5. Retarget Settings": "5. 重定向设置",
    "6. FBX Export": "6. FBX 导出",
    "BVH Motion Retargeter": "BVH 动作重定向",
    "BVH Motion Retargeter {version}": "BVH 动作重定向 {version}",
    "BVH Source File": "BVH 源文件",
    "Source Format": "源格式",
    "Source Mapping": "源骨骼映射",
    "Binding Mode": "绑定方式",
    "Create Target Armature": "新建目标骨架",
    "Bind to Selected Armature": "绑定到所选骨架",
    "Bind to Character Template": "绑定到人物模板",
    "Target Rig Profile": "目标骨架配置",
    "Mixamo Standard": "Mixamo 标准骨架",
    "Unreal Engine 4 Humanoid": "Unreal Engine 4 人形骨架",
    "Unreal Engine 5 Humanoid": "Unreal Engine 5 人形骨架",
    "VRM Humanoid Body": "VRM 人体骨架",
    "Built-in Default Mapping": "内置默认映射",
    "Custom Mapping JSON": "自定义映射 JSON",
    "Character Template": "人物模板",
    "Custom Character File": "自定义人物文件",
    "Custom FBX / VRM": "自定义 FBX / VRM",
    "Default Character": "默认人物",
    "Default White": "白色人物",
    "Default Black": "黑色人物",
    "White": "白色",
    "Black": "黑色",
    "Root Motion Handling": "根运动处理",
    "Root Motion": "根运动",
    "Keep Source Motion": "保留源运动",
    "In-place Animation": "原地动作",
    "Scale by Leg Length": "按腿长缩放",
    "UE5 Root Motion": "UE 根运动",
    "No Root Motion": "固定根骨骼",
    "Root Bone Motion": "根骨骼运动",
    "Pelvis Only": "仅保留骨盆运动",
    "Create UE5 Helper Bones": "生成 UE 辅助骨骼",
    "VRM Leg Axis Correction": "VRM 腿部轴向修正",
    "Left Knee Compensation": "左膝补偿",
    "Right Knee Compensation": "右膝补偿",
    "Left Knee": "左膝",
    "Right Knee": "右膝",
    "FBX Export Preset": "FBX 导出预设",
    "Preset": "预设",
    "Auto": "自动",
    "FBX Output Path": "FBX 输出路径",
    "Auto Export After Convert": "转换后自动导出",
    "Include Mesh": "包含网格",
    "Last Output Armature": "上次输出骨架",
    "Simplify Curves After Bake": "烘焙后精简曲线",
    "Simplify Factor": "曲线精简误差",
    "Match BVH Frame Rate": "匹配 BVH 帧率",
    "VMD Source": "VMD 源文件",
    "VMD Output": "VMD 输出文件",
    "Import To": "导入到",
    "Reference Preview": "参考骨架预览",
    "Selected MMD Rig": "所选 MMD 骨架",
    "VMD Export": "VMD 导出",
    "Preserve Imported VMD": "保留原 VMD 数据",
    "New FK Motion": "新建 FK 动作",
    "FK Mapping": "FK 骨骼映射",
    "Japanese / MMD": "日文 / MMD 骨名",
    "Target Finger Digits": "目标指骨数字格式",
    "Full-width １/２/３": "全角 １/２/３",
    "ASCII 1/2/3": "半角 1/2/3",
    "Blender Units per MMD Unit": "每个 MMD 单位对应的 Blender 单位",
    "Estimate Scale from Reference Legs": "按参考腿长估算比例",
    "Import Start Frame": "导入起始帧",
    "Use VMD 30 FPS": "使用 VMD 30 帧/秒",
    "Overwrite Existing Output": "覆盖已有输出文件",
    "Allow Large Root Discontinuities": "允许根运动大幅跳变",
    "Filter Window (seconds)": "滤波窗口（秒）",
    "Denoise Strength": "去抖强度",
    "Maximum Rotation Change (degrees)": "最大旋转修正（度）",
    "Only Selected Pose Bones": "仅处理选中的姿态骨骼",
    "First Bad Frame": "首个异常帧",
    "Last Bad Frame": "最后异常帧",
    "Root Bone (optional)": "根骨骼（可选）",
    "Confirmed Capture Error in Source Video": "已对照原视频确认捕捉异常",
    "Motion Review / Cleanup": "动作检查与清理",
    "Inspect Export Range": "检查导出区间",
    "Inspect Motion": "检查动作",
    "Create Denoised Copy": "创建去抖副本",
    "Create Root Repair Copy": "创建根运动修复副本",
    "Short Capture Error (up to 150 ms)": "短捕捉异常（最长 150 毫秒）",
    "Import Editable VMD": "导入可编辑 VMD",
    "Export VMD": "导出 VMD",
    "Select VMD Source": "选择 VMD 源文件",
    "Select VMD Output": "选择 VMD 输出文件",
    "Select BVH File": "选择 BVH 文件",
    "Select Character Template": "选择人物模板",
    "Select FBX Output Path": "选择 FBX 输出路径",
    "Select Mapping JSON": "选择映射 JSON",
    "Convert / Retarget BVH": "转换 / 重定向 BVH",
    "Export with Selected Preset": "按所选预设导出",
    "Export Mixamo FBX": "导出 Mixamo FBX",
    "Export UE4 FBX": "导出 UE4 FBX",
    "Export UE5 FBX": "导出 UE5 FBX",
    "Retarget to Selected Armature": "重定向到所选骨架",
    "Retarget to Character Template": "重定向到人物模板",
    "Using built-in default_mixamo_mapping.json": "使用内置 default_mixamo_mapping.json",
    "Built-in mapping file is missing; fallback mapping will be used.": "内置映射文件缺失，将使用默认映射。",
    "Select a custom mapping JSON file.": "请选择自定义映射 JSON 文件。",
    "Built-in character template is missing.": "内置人物模板缺失。",
    "Select the target VRM Armature first.": "请先选择目标 VRM 骨架。",
    "Select a Mixamo-compatible target armature first.": "请先选择兼容 Mixamo 的目标骨架。",
    "Selected VRM armature: {name}": "所选 VRM 骨架：{name}",
    "Selected target: {name}": "所选目标：{name}",
    "Built-in template: {name}": "内置模板：{name}",
    "Last output: {name}": "上次输出：{name}",
    "Solver: Constraint Bake retargeting": "求解方式：约束烘焙重定向",
    "UE profile: root → pelvis → spine_01": "UE 骨架：root → pelvis → spine_01",
    "Optional IK/twist helper bones are non-deforming.": "可选 IK／扭转辅助骨骼不参与网格变形。",
    "VRM profile: Mixamo intermediate rig → J_Bip body bones": "VRM 配置：Mixamo 中间骨架 → J_Bip 人体骨骼",
    "J_Sec secondary hair/skirt/sleeve/accessory bones are ignored.": "不处理 J_Sec 头发、裙摆、袖子和饰物辅助骨骼。",
    "Root travel and default finger tracks are retained.": "保留根位移，默认保留手指轨道。",
    "Needs trusted frames on both sides; no tail prediction.": "异常段前后均需可信帧；不预测缺失的尾段。",
    "FK output: match the actual MMD model rest pose.": "FK 输出需匹配目标 MMD 模型的静止姿态。",
    "Standard leg IK is disabled in new FK files.": "新建 FK 文件会关闭标准腿部 IK。",
    "Reference FK geometry; native MMD IK is not evaluated.": "参考骨架用于 FK 预览，不执行原生 MMD IK。",
    "Use a matching MMD rig for final model proportions.": "使用匹配的 MMD 骨架呈现目标模型比例。",
    "• Stable Constraint Bake retargeting pipeline": "• 约束烘焙重定向",
    "• VMD, Mixamo, UE4/UE5 and VRM Body workflows": "• VMD、Mixamo、UE4/UE5 与 VRM 人体流程",
    "• Black and white Mixamo characters": "• 内置黑、白 Mixamo 人物",
    "• Integrated Mixamo and UE4/UE5 FBX export presets": "• Mixamo 与 UE4/UE5 FBX 导出预设",
    "• VRM body-only mapping with knee compensation controls": "• VRM 人体映射与膝部补偿",
    "Select the source BVH motion capture file.": "选择源 BVH 动捕文件。",
    "Read the BVH frame time and apply the matching frame rate to the Blender scene.": "读取 BVH 帧时长并设置场景帧率。",
    "Choose how the converted motion will be applied.": "选择转换动作的应用方式。",
    "Create a new target-format armature in the current scene.": "在当前场景中新建目标格式骨架。",
    "Retarget the BVH motion to the selected target armature.": "将 BVH 动作重定向到所选目标骨架。",
    "Import a built-in or custom character template and retarget the BVH motion to it.": "导入内置或自定义人物模板并绑定 BVH 动作。",
    "Choose the final target rig naming convention and structure.": "选择目标骨架的命名与层级。",
    "Use the standard mixamorig:* Mixamo bone naming.": "使用标准 mixamorig:* Mixamo 骨名。",
    "UE-style three-spine humanoid for UE4 retargeting; not the Epic mannequin asset.": "使用三节脊柱的 UE 人形骨架进行 UE4 重定向。",
    "Convert to UE-style root/pelvis/spine_01 naming with optional IK/twist helper bones.": "转换为 UE 的 root/pelvis/spine_01 命名，可添加 IK／扭转辅助骨骼。",
    "Retarget to VRM J_Bip body bones while ignoring J_Sec secondary hair, skirt, sleeve, and accessory bones.": "重定向到 VRM J_Bip 人体骨骼，不处理 J_Sec 头发、裙摆、袖子和饰物骨骼。",
    "Choose the source BVH to internal Mixamo mapping configuration.": "选择 BVH 源骨骼到 Mixamo 中间骨架的映射。",
    "Use presets/default_mixamo_mapping.json.": "使用 presets/default_mixamo_mapping.json。",
    "Use a custom BVH-to-Mixamo bone mapping JSON file.": "使用自定义 BVH 到 Mixamo 的骨骼映射 JSON。",
    "Select a custom BVH-to-Mixamo intermediate mapping JSON file.": "选择 BVH 到 Mixamo 中间骨架的自定义 JSON 映射文件。",
    "Choose the character template used by the template-binding workflow.": "选择绑定动作使用的人物模板。",
    "Built-in character template with a white material variant.": "内置白色材质人物模板。",
    "Built-in character template with a black material variant.": "内置黑色材质人物模板。",
    "Built-in white material variant with the same template rig": "共用标准骨架的白色材质人物",
    "Built-in black material variant with the same template rig": "共用标准骨架的黑色材质人物",
    "Use a user-selected FBX, VRM, GLB, or GLTF character template.": "使用自选 FBX、VRM、GLB 或 GLTF 人物模板。",
    "Select a custom FBX, VRM, GLB, or GLTF character file.": "选择自定义 FBX、VRM、GLB 或 GLTF 人物文件。",
    "Control how root/hips translation is transferred during retargeting.": "设置重定向时根骨骼／髋部位移的传递方式。",
    "Keep the original BVH hips translation.": "保留 BVH 原有髋部位移。",
    "Reduce horizontal root motion for loopable game animation.": "减少水平根位移，制作原地循环动作。",
    "Scale root translation using the source/target leg-length ratio.": "按源骨架与目标骨架的腿长比例缩放根位移。",
    "Control root/pelvis translation when converting to the UE5 humanoid profile.": "设置转换为 UE 人形骨架时根骨骼与骨盆的位移。",
    "Keep root stationary while retaining pelvis animation.": "固定根骨骼，保留骨盆动作。",
    "Move horizontal pelvis travel to the root bone.": "将骨盆水平位移分配给根骨骼。",
    "Keep translation on the pelvis without splitting it to the root.": "位移保留在骨盆上，不拆分到根骨骼。",
    "Generate Manny-style IK bones and lightweight twist helper bones. Helper bones are non-deforming by default.": "生成 IK 和轻量扭转辅助骨骼，辅助骨骼默认不参与变形。",
    "Correct VRM thigh front/back local-axis orientation and use knee compensation while preserving the calf and foot chain.": "修正 VRM 大腿前后局部轴向，使用膝部补偿并保留小腿和脚部链。",
    "Fine-tune only the left lower-leg roll to reduce knee seam twisting. Foot and toe bones are preserved.": "微调左小腿轴向，减轻膝部接缝扭转，保留脚与脚趾骨骼。",
    "Fine-tune only the right lower-leg roll. Foot and toe bones are preserved.": "微调右小腿轴向，保留脚与脚趾骨骼。",
    "Choose the FBX export preset. Auto selects Mixamo or UE5 according to the target rig profile.": "选择 FBX 导出预设，自动模式按目标骨架匹配。",
    "Automatically select the export preset from the target rig profile.": "按目标骨架自动选择导出预设。",
    "Use the Mixamo/general FBX export preset.": "使用 Mixamo／通用 FBX 导出设置。",
    "Unreal-oriented animation FBX; retarget to your actual UE4 Skeleton.": "导出 UE 动画 FBX，导入后绑定到项目的 UE4 骨架。",
    "Use Unreal Engine 5 friendly FBX export settings.": "使用适合 Unreal Engine 5 的 FBX 导出设置。",
    "Select the FBX file path used by manual or automatic export.": "设置手动或自动导出的 FBX 文件路径。",
    "Automatically export with the selected FBX preset after a successful conversion.": "转换成功后按所选 FBX 预设自动导出。",
    "Include meshes bound to the armature during FBX export. Disable for animation-only tests.": "导出 FBX 时包含绑定网格；关闭后仅导出动画骨架。",
    "Name of the most recent armature generated or bound by the add-on.": "本插件最近生成或绑定的骨架名称。",
    "Reduce redundant F-curves created by per-frame BVH baking.": "减少 BVH 逐帧烘焙产生的冗余曲线关键帧。",
    "F-curve simplification strength. Higher values produce stronger keyframe reduction.": "曲线减键的允许误差；值越大，保留的关键帧通常越少。",
    "Import editable VMD motion.": "导入可编辑的 VMD 动作。",
    "Convert BVH motion.": "转换 BVH 动作。",
    "Create an explicit generic FK reference; VMD contains no rest skeleton.": "创建通用 FK 参考骨架；VMD 文件不包含静止骨架。",
    "Use Japanese bone names or mmd_bone.name_j on a compatible selected rig.": "按日文骨名或 mmd_bone.name_j 绑定所选兼容骨架。",
    "Patch edited mapped bones, retaining all untouched sections.": "更新已编辑骨轨道，保留未编辑的数据区段。",
    "Create explicit FK channels from a mapped rig; target rest and IK settings must match.": "从已映射骨架创建 FK 轨道，并匹配目标模型的静止姿态与 IK 设置。",
    "Map mixamorig:* or source body bone names.": "映射 mixamorig:* 或源人体骨名。",
    "Use Japanese/VMD-labelled bone names.": "使用日文骨名或骨架声明的 VMD 名称。",
    "Common MMD and supplied capture names.": "使用常见 MMD 全角数字指骨名称。",
    "Use only when these names match the target model.": "选择与目标模型一致的数字命名。",
    "For new FK output only: match source leg length to the generic reference. Calibrate to the actual MMD model for final use.": "用于新建 FK 输出：按参考骨架腿长匹配比例，可按目标模型校准。",
    "Explicitly permit reviewed cuts/teleports in new exports; otherwise severe root steps block export.": "允许已确认的切镜／瞬移；默认阻止严重根运动跳变的导出。",
    "Confirm these short samples are capture errors, with trusted samples on both sides. Actual jumps and camera cuts must not be reconstructed.": "对照原视频确认短段捕捉异常，并确保前后有可信帧；真实跳跃和切镜不进行插值修复。",
    "Select a BVH motion capture file.": "选择 BVH 动捕文件。",
    "Select a custom BVH-to-Mixamo mapping JSON file.": "选择自定义 BVH 到 Mixamo 的 JSON 映射。",
    "Select a custom FBX, VRM, GLB, or GLTF character template.": "选择自定义 FBX、VRM、GLB 或 GLTF 人物模板。",
    "Select the FBX output file path for Mixamo or UE5 export.": "设置 Mixamo 或 UE 的 FBX 输出路径。",
    "Convert BVH motion to Mixamo, UE5, or VRM-compatible target rigs.": "将 BVH 动作转换到 Mixamo、UE4/UE5 或 VRM 兼容骨架。",
    "Export the current or most recent output armature using the selected FBX export preset.": "按所选 FBX 预设导出当前骨架。",
    "Export the current or most recent output armature with the Mixamo/general FBX preset.": "按 Mixamo／通用 FBX 预设导出当前骨架。",
    "Export the current or most recent output armature with the built-in UE5 FBX preset.": "按内置 UE5 FBX 预设导出当前骨架。",
    "Export an Unreal-style humanoid FBX. Retarget to the actual UE4 skeleton in Unreal.": "导出 UE 人形骨架 FBX，并在 Unreal 中绑定目标 UE4 骨架。",
    "Import VMD to an FK reference or selected Japanese-named rig, retaining original sections for export.": "将 VMD 导入参考骨架或所选日文骨架，保留原数据供导出。",
    "Preserve the imported VMD sections, or explicitly create a new mapped FK motion.": "保留原 VMD 数据导出，或从映射骨架创建新的 FK 动作。",
    "Choose an existing .vmd source file.": "请选择已有的 .vmd 源文件。",
    "VMD imported: {count} editable bone tracks. Original extra tracks retained.": "VMD 已导入：{count} 条可编辑骨轨道，其余原始轨道已保留。",
    "VMD exported. See the motion report for retained tracks and FK limits.": "VMD 已导出，保留轨道详情见动作报告。",
    "Root discontinuity candidates: {frames}": "根运动跳变候选帧：{frames}",
    "No large root steps in the export range. See Motion Report.": "导出区间未发现大幅根运动跳变，详情见动作报告。",
    "Created a bounded rotation-cleanup copy. Translation and default-excluded fingers are retained.": "已创建有界旋转去抖副本，保留位移，默认保留手指轨道。",
    "Created a short root-gap repair copy. Review it against the source video.": "已创建短段根运动修复副本，请对照原视频查看。",
    "Create or select an Armature first, or complete one conversion before exporting.": "请先创建或选择骨架，或完成一次动作转换。",
    "Set the FBX output path first.": "请先设置 FBX 输出路径。",
    "{label} FBXexport completed: {path}": "{label} FBX 已导出：{path}",
    "FBX export failed: {error}": "FBX 导出失败：{error}",
    "Select a BVH source file first.": "请先选择 BVH 源文件。",
    "Select a valid .bvh file.": "请选择有效的 .bvh 文件。",
    "VRM retargeting requires a selected VRM Armature.": "请先选择目标 VRM 骨架。",
    "Bind-to-selected mode requires a selected Mixamo-compatible armature.": "绑定到所选骨架时，请先选择兼容 Mixamo 的骨架。",
    "Failed to load bone mapping JSON: {error}": "加载骨骼映射 JSON 失败：{error}",
    "BVH import failed. Check the file path and BVH format.": "BVH 导入失败，请检查文件路径和格式。",
    "The selected mapping does not match the BVH skeleton. Check the preset or custom JSON.": "所选映射与 BVH 骨架不匹配，请检查预设或自定义 JSON。",
    "Critical bone coverage is insufficient. Compatibility score {score}/100": "缺少必要骨骼，兼容性评分 {score}/100。",
    "Animation data may be incomplete. Please inspect the imported BVH.": "动画数据可能不完整，请检查导入的 BVH。",
    "VRM Humanoid Body requires binding to a selected/imported VRM armature; creating an empty VRM rig is not supported.": "VRM 人体模式需要绑定到所选或已导入的 VRM 骨架。",
    "Auto export is enabled, but no FBX output path is set.": "已启用自动导出，请设置 FBX 输出路径。",
    "Created target rig: {name} | Compatibility score {score}/100": "已创建目标骨架：{name}；兼容性评分 {score}/100。",
    "Character template import failed: {error}": "人物模板导入失败：{error}",
    "Missing critical VRM body bones: {names}": "缺少必要的 VRM 人体骨骼：{names}",
    "Target armature is missing some mapped bones; retarget quality may be affected: {count} bones": "目标骨架缺少 {count} 根映射骨骼。",
    "Animation retargeting failed.": "动作重定向失败。",
    "BVH animation retargeted to {name} | Target: {target} | Root: {root}": "BVH 已重定向到 {name}；目标：{target}；根运动：{root}",
    "Processing failed: {error}": "处理失败：{error}",
}

# Core validation messages share the interface catalog.
TRANSLATIONS.update(ERROR_TRANSLATIONS)
_ENUM_TABLES = {}
_ENUM_CACHE = {}
_ENUM_CALLBACKS = {}
_ACTIVE_LANGUAGE = None
_REGISTERED = False
_FORMATTER = string.Formatter()


def language(context=None, scene=None):
    if scene is None:
        scene = getattr(context, "scene", None)
    if scene is None and bpy is not None:
        scene = getattr(bpy.context, "scene", None)
    selected = getattr(scene, "bvh_ui_language", "AUTO") if scene is not None else "AUTO"
    if selected in {"zh_CN", "en_US"}:
        return selected
    preferences = getattr(context, "preferences", None)
    if preferences is None and bpy is not None:
        preferences = getattr(bpy.context, "preferences", None)
    locale = getattr(getattr(preferences, "view", None), "language", "en_US")
    if locale in {"DEFAULT", "AUTO", ""} and bpy is not None:
        locale = getattr(bpy.app.translations, "locale", "en_US")
    return "zh_CN" if str(locale).lower().startswith("zh") else "en_US"


def _render(template, values):
    def replace(match):
        field, spec = match.group(1), match.group(2)
        if field not in values:
            return match.group(0)
        value = values[field]
        # Captured rendered values keep their spelling, unit, path and precision.
        if isinstance(value, _Captured):
            return str(value)
        return format(value, spec[1:] if spec else "")

    return re.sub(r"\{([A-Za-z_][A-Za-z_0-9]*)(:[^{}]+)?\}", replace, template)


class _Captured(str):
    pass


def _compile_template(template):
    pieces = []
    seen = set()
    for literal, field, _spec, _conversion in _FORMATTER.parse(template):
        pieces.append(re.escape(literal))
        if field is not None:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", field):
                return None
            if field in seen:
                pieces.append(f"(?P={field})")
            else:
                pieces.append(f"(?P<{field}>.+?)")
                seen.add(field)
    return re.compile("^" + "".join(pieces) + "$", re.DOTALL) if seen else None


_TEMPLATE_RULES = []
for _english, _chinese in TRANSLATIONS.items():
    for _source, _target, _target_lang in [
        (_english, _chinese, "zh_CN"),
        (_chinese, _english, "en_US"),
        (_english, _english, "en_US"),
        (_chinese, _chinese, "zh_CN"),
    ]:
        _pattern = _compile_template(_source)
        if _pattern is not None:
            _TEMPLATE_RULES.append((_pattern, _target, _target_lang, len(_source)))
_TEMPLATE_RULES.sort(key=lambda item: item[3], reverse=True)
_REVERSE = {value: key for key, value in TRANSLATIONS.items()}


def tr(message, context=None, **values):
    if not isinstance(message, str):
        message = str(message)
    selected = language(context)
    if selected == "zh_CN":
        template = TRANSLATIONS.get(message)
    else:
        template = _REVERSE.get(message)
    if template is not None:
        return _render(template, values)
    if values:
        return _render(message, values)
    # Report strings from existing f-strings use a bounded catalog template match.
    for pattern, target, target_lang, _length in _TEMPLATE_RULES:
        if target_lang != selected:
            continue
        matched = pattern.fullmatch(message)
        if matched:
            captures = {key: _Captured(value) for key, value in matched.groupdict().items()}
            if "error" in captures:
                captures["error"] = _Captured(tr(str(captures["error"]), context))
            if "label" in captures:
                label = str(captures["label"])
                captures["label"] = _Captured(
                    TRANSLATIONS.get(label, label) if selected == "zh_CN" else _REVERSE.get(label, label)
                )
            return _render(target, captures)
    return message


def translated_report(context, reporter, levels, message, **values):
    return reporter(levels, tr(message, context, **values))


def translated_exception(error, context=None):
    return tr(str(error), context)


class LocalizedOperator:
    bl_translation_context = CONTEXT

    @classmethod
    def description(cls, context, properties):
        return tr(getattr(cls, "bl_description", "") or getattr(cls, "bl_label", ""), context)


def localized_enum(*, items, **kwargs):
    """Keep identifiers and numeric values stable while localizing visible items."""
    source = []
    for index, item in enumerate(items):
        if len(item) == 3:
            source.append((*item, index))
        elif len(item) in {4, 5}:
            source.append(tuple(item))
        else:
            raise ValueError("Unsupported enum item shape")
    key = kwargs.get("name", str(len(_ENUM_TABLES)))
    _ENUM_TABLES[key] = tuple(source)
    default = kwargs.get("default")
    if isinstance(default, str):
        matched = next((item for item in source if item[0] == default), None)
        if matched is None:
            raise ValueError("Enum default must name a declared identifier")
        kwargs["default"] = matched[-1]

    def callback(self, context):
        selected = language(context, scene=self if hasattr(self, "bvh_ui_language") else None)
        cache_key = (key, selected)
        if cache_key not in _ENUM_CACHE:
            translated = []
            for item in _ENUM_TABLES[key]:
                identifier, label, description, *rest = item
                visible_label = TRANSLATIONS.get(label, label) if selected == "zh_CN" else _REVERSE.get(label, label)
                visible_description = (
                    TRANSLATIONS.get(description, description)
                    if selected == "zh_CN"
                    else _REVERSE.get(description, description)
                )
                translated.append((identifier, visible_label, visible_description, *rest))
            _ENUM_CACHE[cache_key] = tuple(translated)
        return _ENUM_CACHE[cache_key]

    _ENUM_CALLBACKS[key] = callback
    from bpy.props import EnumProperty

    return EnumProperty(items=callback, translation_context=CONTEXT, **kwargs)


def localized_property(factory, **kwargs):
    return factory(translation_context=CONTEXT, **kwargs)


def sync_translations(context=None, scene=None):
    global _ACTIVE_LANGUAGE, _REGISTERED
    if bpy is None:
        return
    selected = language(context, scene=scene)
    if selected == _ACTIVE_LANGUAGE and _REGISTERED:
        return
    if _REGISTERED:
        bpy.app.translations.unregister(DOMAIN)
    mapping = {(CONTEXT, key): value if selected == "zh_CN" else key for key, value in TRANSLATIONS.items()}
    locales = set(getattr(bpy.app.translations, "locales", ())) | {"en_US", "zh_CN", "zh_HANS", "en_GB"}
    bpy.app.translations.register(DOMAIN, {locale: mapping for locale in locales})
    _ACTIVE_LANGUAGE = selected
    _REGISTERED = True


def language_changed(self=None, context=None):
    sync_translations(context, scene=self if hasattr(self, "bvh_ui_language") else None)
    wm = getattr(context, "window_manager", None) if context is not None else None
    if wm is None and bpy is not None:
        wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", ()):
        for area in window.screen.areas:
            area.tag_redraw()


def register_i18n():
    sync_translations()


def unregister_i18n():
    global _REGISTERED, _ACTIVE_LANGUAGE
    if bpy is not None and _REGISTERED:
        bpy.app.translations.unregister(DOMAIN)
    _REGISTERED = False
    _ACTIVE_LANGUAGE = None


class TranslatedLayout:
    """Small UILayout proxy; data and operator identifiers pass through intact."""

    def __init__(self, layout, context):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_context", context)
        sync_translations(context)

    def __getattr__(self, name):
        return getattr(self._layout, name)

    def __setattr__(self, name, value):
        if name in {"_layout", "_context"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._layout, name, value)

    def t(self, message, **values):
        return tr(message, self._context, **values)

    def box(self):
        return type(self)(self._layout.box(), self._context)

    def row(self, **kwargs):
        return type(self)(self._layout.row(**kwargs), self._context)

    def column(self, **kwargs):
        return type(self)(self._layout.column(**kwargs), self._context)

    def label(self, *, text="", **kwargs):
        return self._layout.label(text=self.t(text), translate=False, **kwargs)

    def prop(self, data, property, **kwargs):
        if "text" not in kwargs:
            prop = data.bl_rna.properties.get(property)
            kwargs["text"] = getattr(prop, "name", property)
        kwargs["text"] = self.t(kwargs["text"])
        return self._layout.prop(data, property, translate=False, **kwargs)

    def operator(self, identifier, **kwargs):
        if "text" not in kwargs:
            module, name = identifier.split(".", 1)
            try:
                kwargs["text"] = getattr(getattr(bpy.ops, module), name).get_rna_type().name
            except (AttributeError, RuntimeError):
                kwargs["text"] = identifier
        kwargs["text"] = self.t(kwargs["text"])
        return self._layout.operator(identifier, translate=False, **kwargs)
