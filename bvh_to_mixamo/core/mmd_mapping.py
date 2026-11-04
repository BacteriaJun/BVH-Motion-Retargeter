"""Explicit VMD-name to Blender-name bindings. No automatic PMX rig invention."""


def mixamo_mapping(armature, finger_digits="FULLWIDTH"):
    if finger_digits not in {"FULLWIDTH", "ASCII"}:
        raise ValueError("Choose FULLWIDTH or ASCII finger digits for the target MMD model.")
    digit = str.maketrans("0123456789", "０１２３４５６７８９")
    pairs = {
        "センター": "Hips",
        "上半身": "Spine",
        "上半身2": "Spine1",
        "上半身3": "Spine2",
        "首": "Neck",
        "頭": "Head",
    }
    for side, jp in [("Left", "左"), ("Right", "右")]:
        for name, key in [
            ("Shoulder", "肩"),
            ("Arm", "腕"),
            ("ForeArm", "ひじ"),
            ("Hand", "手首"),
            ("UpLeg", "足"),
            ("Leg", "ひざ"),
            ("Foot", "足首"),
            ("ToeBase", "つま先"),
        ]:
            pairs[jp + key] = side + name
        for finger, japanese in [
            ("Thumb", "親指"),
            ("Index", "人指"),
            ("Middle", "中指"),
            ("Ring", "薬指"),
            ("Pinky", "小指"),
        ]:
            for number in range(1, 4):
                mmd_number = number - 1 if finger == "Thumb" else number
                name = jp + japanese + str(mmd_number)
                if finger_digits == "FULLWIDTH":
                    name = name.translate(digit)
                pairs[name] = side + "Hand" + finger + str(number)
    result = {}
    for japanese, name in pairs.items():
        actual = next(
            (candidate for candidate in ("mixamorig:" + name, name) if candidate in armature.data.bones), None
        )
        if actual:
            result[japanese] = actual
    if "センター" not in result:
        raise ValueError(
            "The Mixamo FK mapping needs a Hips bone. Use Japanese bone names or an explicit mapping for other rigs."
        )
    return result
