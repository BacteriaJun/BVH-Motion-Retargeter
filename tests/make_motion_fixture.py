"""Generate original, synthetic test motion; no customer capture in the repo."""

import math
from pathlib import Path


def write_fixture(path):
    def node(name, offset, children=()):
        return (name, offset, children)

    def finger(side):
        return node(side + "HandIndex1", (0.08 if side == "Left" else -0.08, 0, 0))

    def arm(side, sign):
        return node(
            side + "Shoulder",
            (sign * 0.10, 0.05, 0),
            [
                node(
                    side + "Arm",
                    (sign * 0.12, 0, 0),
                    [
                        node(
                            side + "ForeArm",
                            (sign * 0.25, 0, 0),
                            [node(side + "Hand", (sign * 0.25, 0, 0), [finger(side)])],
                        )
                    ],
                )
            ],
        )

    def leg(side, sign):
        return node(
            side + "UpLeg",
            (sign * 0.12, -0.10, 0),
            [
                node(
                    side + "Leg",
                    (0, -0.45, 0.015),
                    [node(side + "Foot", (0, -0.45, -0.015), [node(side + "ToeBase", (0, 0, 0.15))])],
                )
            ],
        )

    tree = node(
        "Hips",
        (0, 1, 0),
        [
            node(
                "Spine",
                (0, 0.15, 0),
                [
                    node(
                        "Spine1",
                        (0, 0.15, 0),
                        [
                            node(
                                "Spine2",
                                (0, 0.15, 0),
                                [
                                    node("Neck", (0, 0.10, 0), [node("Head", (0, 0.10, 0))]),
                                    arm("Left", 1),
                                    arm("Right", -1),
                                ],
                            )
                        ],
                    )
                ],
            ),
            leg("Left", 1),
            leg("Right", -1),
        ],
    )
    lines = ["HIERARCHY"]
    order = []

    def emit(item, depth=0):
        name, offset, children = item
        pad = "  " * depth
        order.append(name)
        lines.extend(
            [
                pad + ("ROOT " if depth == 0 else "JOINT ") + name,
                pad + "{",
                pad + "  OFFSET " + " ".join(map(str, offset)),
                pad
                + "  CHANNELS "
                + (
                    "6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"
                    if depth == 0
                    else "3 Zrotation Xrotation Yrotation"
                ),
            ]
        )
        for child in children:
            emit(child, depth + 1)
        if not children:
            lines.extend([pad + "  End Site", pad + "  {", pad + "    OFFSET 0 0.05 0", pad + "  }"])
        lines.append(pad + "}")

    emit(tree)
    lines.extend(["MOTION", "Frames: 61", "Frame Time: 0.03333333333333333"])
    for i in range(61):
        t = i / 30
        values = [0.1 * t, 1 + 0.015 * math.sin(2 * math.pi * t), 0]
        for name in order:
            angle = (
                (8 * math.sin(t * math.pi) + 3 * (-1) ** i)
                if name == "LeftArm"
                else (10 * math.sin(t * math.pi) if name.endswith("Index1") else 0)
            )
            values.extend([angle, 0, 0])
        lines.append(" ".join(f"{x:.9f}" for x in values))
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    write_fixture(Path(__file__).parent / "fixtures/synthetic_motion.bvh")
