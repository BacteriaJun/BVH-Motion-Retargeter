"""Action access shared by legacy Blender 4.2 and layered Blender 4.4+ actions."""


def action_fcurve_collection(action, owner=None, create=True):
    if action is None:
        raise ValueError("An Action is required.")
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return legacy
    slot = None
    if owner is not None and owner.animation_data and owner.animation_data.action == action:
        slot = getattr(owner.animation_data, "action_slot", None)
    if slot is None and len(action.slots) == 1:
        slot = action.slots[0]
    if slot is None and create and owner is not None:
        slot = action.slots.new(id_type=owner.id_type, name=owner.name)
        owner.animation_data.action_slot = slot
    if slot is None:
        raise ValueError("A layered Action needs an unambiguous owner/slot.")
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type == "KEYFRAME":
                bag = strip.channelbag(slot, ensure=False)
                if bag is not None:
                    return bag.fcurves
    if not create:
        return ()
    layer = action.layers[0] if len(action.layers) else action.layers.new("Motion")
    strip = next((s for s in layer.strips if s.type == "KEYFRAME"), None)
    if strip is None:
        strip = layer.strips.new(type="KEYFRAME")
    return strip.channelbag(slot, ensure=True).fcurves


def iter_action_fcurves(action, owner=None):
    if action is None:
        return iter(())
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return iter(legacy)
    if owner is not None:
        slot = getattr(owner.animation_data, "action_slot", None) if owner.animation_data else None
        if slot is not None:
            curves = []
            for layer in action.layers:
                for strip in layer.strips:
                    if strip.type == "KEYFRAME":
                        bag = strip.channelbag(slot, ensure=False)
                        if bag is not None:
                            curves.extend(bag.fcurves)
            return iter(curves)
    # Read-only operations such as path renaming may visit every slot.
    return iter(
        fc
        for layer in action.layers
        for strip in layer.strips
        if strip.type == "KEYFRAME"
        for bag in strip.channelbags
        for fc in bag.fcurves
    )


def copy_action_for_edit(owner, suffix="_Edited"):
    if not owner.animation_data or not owner.animation_data.action:
        raise ValueError("The selected armature has no active Action.")
    source = owner.animation_data.action
    copied = source.copy()
    copied.name = source.name + suffix
    owner.animation_data.action = copied
    return copied


def pose_bone_selected(pose_bone):
    """Blender 5.1 moved pose selection from Bone to PoseBone."""
    return bool(pose_bone.select if hasattr(pose_bone, "select") else pose_bone.bone.select)


def set_pose_bone_selected(pose_bone, selected):
    if hasattr(pose_bone, "select"):
        pose_bone.select = bool(selected)
    else:
        pose_bone.bone.select = bool(selected)
