# Mixamo character templates / Mixamo 人物模板

The add-on includes two characters: **White** (default) and **Black**. Both use a Mixamo-compatible rig. Custom FBX, VRM, GLB and GLTF character files can also be selected in the add-on.

插件内置**白色**（默认）和**黑色**两个人物，均使用 Mixamo 兼容骨架。也可选择自定义 FBX、VRM、GLB 或 GLTF 人物。

The FBX assets are included in the installation ZIP. To prepare a source checkout, run:

安装 ZIP 已包含两个 FBX。准备源码工程时运行：

```sh
python scripts/fetch_templates.py
```

The script retrieves only the black and white templates from the pinned v3.2.0 asset archive and verifies their SHA-256 hashes. Existing verified files are reused.

脚本从固定版本的 v3.2.0 资源包中提取黑白两个模板，并核对 SHA-256；本地已有且校验正确的文件会直接复用。
