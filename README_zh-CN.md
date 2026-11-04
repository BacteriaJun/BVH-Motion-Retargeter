# BVH Motion Retargeter

[![Release](https://img.shields.io/github/v/release/BacteriaJun/BVH-Motion-Retargeter)](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest)
[![CI](https://github.com/BacteriaJun/BVH-Motion-Retargeter/actions/workflows/ci.yml/badge.svg)](https://github.com/BacteriaJun/BVH-Motion-Retargeter/actions/workflows/ci.yml)
[![Blender](https://img.shields.io/badge/Blender-4.2%2B-orange)](https://www.blender.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) | **简体中文**

**BVH Motion Retargeter 4.0.0** 是 Blender 动作处理插件，提供 VMD 精修、BVH 重定向、动作清理，以及 Mixamo、UE4／UE5 FBX 导出。

## 4.0.0 新增功能

- **VMD 精修闭环**：将骨骼与控制轨道导入 Blender，编辑 Action 后回导；保留未改动的骨骼、表情、相机、光照、阴影和 IK 开关记录。
- **新建 FK VMD**：将映射后的 BVH／Mixamo 动作按 VMD 的 30 Hz 时间基准导出，并设置标准腿部／脚尖 IK 开关。
- **动作清理**：创建有界旋转去抖副本，以及经视频确认的短段 root 修复副本，保留原对象和原 Action。
- **FBX 与 Root Motion**：提供 Mixamo、UE4、UE5 导出配置；按世界坐标分配水平 root 运动，保留采样后的身体轨迹与高度。
- **中英文界面**：在插件内选择自动、简体中文或 English。
- **黑白两个人物模板**：保留黑色、白色 Mixamo 兼容模型，并支持自定义 FBX／VRM／GLB／GLTF 角色。

## 安装与语言切换

环境要求：**Blender 4.2 或更高版本**。本机原生回归已在 macOS arm64 的 **Blender 4.2.0** 和 **5.1.2** 运行。

1. 前往 [GitHub Releases](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest) 下载安装 ZIP。
2. 在 Blender 打开 **编辑 → 偏好设置 → 插件／扩展 → 从磁盘安装**（**Edit → Preferences → Add-ons / Extensions → Install from Disk**）。
3. 选择 ZIP，启用 **BVH Motion Retargeter**。
4. 在 **3D 视图 → N 侧栏 → BVH Retarget** 打开插件。
5. 在面板顶部的 **界面语言 / Language** 选择 **自动 / Auto**、**简体中文** 或 **English**。自动模式跟随 Blender 界面语言；此设置作用于本插件界面。

## 精修已有 VMD

1. 选择 **VMD** 和源文件。
2. 选择 **参考骨架预览 / Reference Preview** 创建参考骨架，或选择 **所选 MMD 骨架 / Selected MMD Rig** 使用兼容模型骨架。
3. 点击 **导入可编辑 VMD / Import Editable VMD**。
4. 在 Blender 编辑骨骼／控制轨道，或使用 **创建去抖副本 / Create Denoised Copy**。保存 `.blend` 可保留原始 VMD 和编辑会话。
5. 选择 **保留原 VMD 数据 / Preserve Imported VMD**，导出到新文件。

未修改时，导出结果与原始 VMD 字节一致。已修改的映射轨道按 30 Hz 重采样；其余轨道和 VMD 段保留原始记录。全角／半角指骨数字可自动匹配，源名称保留。

参考骨架用于 FK／控制轨道编辑，原始 IK 开关字段予以保留。模型相关的 IK、附加变形、表情和物理效果由对应 MMD／PMX 模型环境呈现。

从其他骨架创建新动作时，选择 **新建 FK 动作 / New FK Motion**，匹配目标 MMD 骨名、静止姿态轴向和单位后导出。新 FK 文件默认关闭标准腿部／脚尖 IK。

映射、采样与导出条件见 [VMD 精修与导出说明](docs/vmd-workflow.md)。

## BVH 重定向与 FBX 导出

1. 选择 `.bvh` 文件，以及内置或自定义 JSON 源骨骼映射。
2. 选择 **Mixamo Standard**、**Unreal Engine 4 Humanoid**、**Unreal Engine 5 Humanoid** 或 **VRM Humanoid Body**。
3. 创建目标骨架、绑定已选兼容骨架，或选择人物模板。
4. 执行重定向与烘焙，生成目标骨架上可继续编辑的 Action。
5. 使用 **Mixamo FBX**、**UE4 FBX**、**UE5 FBX** 或 **Auto** 导出。

插件可将场景帧率与源 BVH 匹配。FBX 配置逐帧采样，并关闭导出器关键帧缩减。Unreal 输出采用通用人形层级与 root，在引擎项目中使用目标 Skeleton 与重定向设置。VRM 只映射人体骨骼，`J_Sec_*` 附件／物理骨骼保留在人体映射之外。

## 动作清理与 Root Motion

- **创建去抖副本 / Create Denoised Copy**：在独立对象／Action 上执行有界 SO(3) 旋转滤波，默认保留 root 位移、手指和 IK 控制旋转，也可只处理选中的 Pose Bones。
- **检查导出区间 / Inspect Export Range**：定位选定范围内的大幅 root 跳变和无效动画数据。
- **创建根运动修复副本 / Create Root Repair Copy**：对经视频确认、两侧有可信样本的 ≤150 ms 异常段进行插值。损坏的尾段需通过审查确定导出范围。
- 新建 Unreal root 位于模型原点，按世界 X／Y 方向分配水平运动，保留身体高度与采样后的身体轨迹；已有 root 保留原静止几何。
- 覆盖已有输出文件需要显式选择。

详见 [Root Motion 与 FBX 验证](docs/root-motion-validation.md)。

## 人物模板

安装包内置 **黑色 / Black** 和 **白色 / White** 两个 Mixamo 兼容角色；**自定义 / Custom** 可加载自己的 FBX、VRM、GLB 或 GLTF 模型。旧版 Default、Pink、Purple、Green 选择会迁移为 White。

源码工程通过 SHA256 校验获取这两个模板：

```sh
python scripts/fetch_templates.py
```

## 开发与构建

```sh
git clone https://github.com/BacteriaJun/BVH-Motion-Retargeter.git
cd BVH-Motion-Retargeter
python -m pip install ruff==0.14.4
python scripts/fetch_templates.py
ruff check .
python -m compileall -q bvh_to_mixamo scripts tests
python -m unittest discover -s tests -v
python scripts/build_release.py
```

安装 ZIP 生成于 `dist/`。运行时代码位于 `bvh_to_mixamo/`；文档、测试、构建工具和 CI 分别维护在 `docs/`、`tests/`、`scripts/` 与工作流目录中。构建会校验两个模板的哈希、包内文件清单和版本一致性，并生成可重复的 ZIP 字节。

CI 配置包含仓库检查，以及 Linux／Windows 上的 Blender 4.2.0／5.1.2 原生回归，覆盖 VMD、动作清理、FBX、重定向、人物绑定、操作器、语言切换、模板迁移和隔离安装。

## 文档

- [用户指南](docs/user-guide.md)
- [VMD 精修与导出](docs/vmd-workflow.md)
- [VMD 格式与插值](docs/vmd-format-notes.md)
- [Root Motion 与 FBX 验证](docs/root-motion-validation.md)
- [发布检查与复现命令](docs/release-readiness.md)
- [更新记录](CHANGELOG.md)
- [参与贡献](CONTRIBUTING.md)

**作者：** Junius Tang / [BacteriaJun](https://github.com/BacteriaJun)

**许可：** [MIT](LICENSE)
