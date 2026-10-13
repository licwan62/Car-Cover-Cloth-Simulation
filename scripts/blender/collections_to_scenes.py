import bpy

# ==========================================
# 配置
# ==========================================

# False：每个第一层 Collection 生成一个 Scene（子 Collection 保留在其中）
# True ：子 Collection 也各自生成 Scene；父 Collection 的 Scene 只放它直接包含的 Object
SPLIT_SUB_COLLECTIONS = False

# 已存在同名 Scene 时：True 删除后重建，False 跳过
REPLACE_EXISTING = False

# ==========================================
# 收集目标
# ==========================================

source = bpy.context.scene

# (Scene 名, 要链接的 Collection 或 None, 要直接链接的 Object 列表)
targets = []

for parent in source.collection.children:

    if not SPLIT_SUB_COLLECTIONS or not parent.children:
        targets.append((parent.name, parent, []))
        continue

    if parent.objects:
        targets.append((parent.name, None, list(parent.objects)))

    for child in parent.children:
        targets.append((child.name, child, []))

print(f"源 Scene：{source.name}，目标 Scene：{len(targets)} 个")

# ==========================================
# 生成 Scene
# ==========================================

created = 0
skipped = 0

for name, collection, objects in targets:

    existing = bpy.data.scenes.get(name)

    if existing is source:
        print(f"  [SKIP] {name}（与源 Scene 同名）")
        skipped += 1
        continue

    if existing:
        if not REPLACE_EXISTING:
            print(f"  [SKIP] {name}（Scene 已存在）")
            skipped += 1
            continue
        bpy.data.scenes.remove(existing)

    # 链接复制：沿用源 Scene 的渲染、单位、World 等设置，与源 Scene 共享 Collection/Object
    scene = source.copy()
    scene.name = name
    root = scene.collection

    for child in list(root.children):
        root.children.unlink(child)

    for obj in list(root.objects):
        root.objects.unlink(obj)

    if collection:
        root.children.link(collection)

    for obj in objects:
        root.objects.link(obj)

    created += 1
    count = len(root.all_objects)
    print(f"  [SCENE] {scene.name}  Object：{count}")

# ==========================================
# 结果
# ==========================================

print("\n========== 完成 ==========")
print(f"新建 Scene：{created}")
print(f"跳过：{skipped}")
print("源 Scene 未修改；所有新 Scene 与源 Scene 共享数据，修改 Object 会同步。")
