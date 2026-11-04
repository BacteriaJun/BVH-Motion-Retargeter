"""Bounded SO(3) denoising and short-gap interpolation, standard library only.

No contact is inferred here. Translation is preserved by rotational denoising.
The filter is local in quaternion tangent space and protects large motion steps.
"""

import math


def finite_positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive.")


def normalize(q):
    if len(q) != 4 or not all(math.isfinite(v) for v in q):
        raise ValueError("Expected a finite quaternion (w,x,y,z).")
    norm = math.sqrt(sum(v * v for v in q))
    if norm < 1e-12:
        raise ValueError("Zero quaternion.")
    return tuple(v / norm for v in q)


def multiply(a, b):
    w, x, y, z = a
    v, p, q, r = b
    return (
        w * v - x * p - y * q - z * r,
        w * p + x * v + y * r - z * q,
        w * q - x * r + y * v + z * p,
        w * r + x * q - y * p + z * v,
    )


def log_relative(a, b):
    q = multiply((a[0], -a[1], -a[2], -a[3]), b)
    if q[0] < 0:
        q = tuple(-v for v in q)
    n = math.sqrt(sum(v * v for v in q[1:]))
    gain = 2 * math.atan2(n, max(q[0], 0)) / n if n > 1e-12 else 2.0
    return tuple(v * gain for v in q[1:])


def exp_vector(v):
    angle = math.sqrt(sum(x * x for x in v))
    gain = math.sin(angle / 2) / angle if angle > 1e-12 else 0.5
    return (math.cos(angle / 2), *(x * gain for x in v))


def distance_degrees(a, b):
    return math.degrees(math.sqrt(sum(v * v for v in log_relative(normalize(a), normalize(b)))))


def _solve(matrix, vector):
    rows = [list(r) + [v] for r, v in zip(matrix, vector)]
    for k in range(len(rows)):
        pivot = max(range(k, len(rows)), key=lambda j: abs(rows[j][k]))
        rows[k], rows[pivot] = rows[pivot], rows[k]
        if abs(rows[k][k]) < 1e-14:
            raise ValueError("Degenerate interpolation system.")
        divisor = rows[k][k]
        rows[k] = [v / divisor for v in rows[k]]
        for j in range(len(rows)):
            if j != k:
                gain = rows[j][k]
                rows[j] = [a - gain * b for a, b in zip(rows[j], rows[k])]
    return [r[-1] for r in rows]


def denoise_quaternions(values, fps, window_seconds=0.12, strength=0.5, cap_degrees=3.0, protected=None):
    """Quadratic local fit. Large angular steps and explicit guards abstain.

    `protected` has one boolean per frame. First/last radius frames stay exact;
    no claim is made about velocities/accelerations beyond sampled frames.
    """
    finite_positive(fps, "fps")
    finite_positive(window_seconds, "window_seconds")
    finite_positive(cap_degrees, "cap_degrees")
    if isinstance(strength, bool) or not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("strength must be in [0,1].")
    qs = [normalize(q) for q in values]
    n = len(qs)
    guards = [False] * n if protected is None else list(protected)
    if len(guards) != n or any(type(v) is not bool for v in guards):
        raise ValueError("protected must be a boolean per source sample.")
    radius = max(2, int(round(window_seconds * fps / 2)))
    radius = min(radius, 60)
    cuts = [i for i in range(1, n) if distance_degrees(qs[i - 1], qs[i]) > 45]
    for cut in cuts:
        for j in range(max(0, cut - radius), min(n, cut + radius + 1)):
            guards[j] = True
    xs = [j / radius for j in range(-radius, radius + 1)]
    weights = [math.exp(-2 * x * x) for x in xs]
    design = [[1.0, x, x * x] for x in xs]
    gram = [[sum(w * r[a] * r[b] for r, w in zip(design, weights)) for b in range(3)] for a in range(3)]
    out = list(values)
    changed = 0
    for i in range(radius, n - radius):
        if any(guards[i - radius : i + radius + 1]):
            continue
        offsets = [log_relative(qs[i], q) for q in qs[i - radius : i + radius + 1]]
        tangent = [
            _solve(gram, [sum(w * r[k] * v[axis] for r, w, v in zip(design, weights, offsets)) for k in range(3)])[0]
            for axis in range(3)
        ]
        tangent = [v * strength for v in tangent]
        length = math.sqrt(sum(v * v for v in tangent))
        gain = min(1.0, math.radians(cap_degrees) / max(length, 1e-15))
        result = normalize(multiply(qs[i], exp_vector([v * gain for v in tangent])))
        if sum(a * b for a, b in zip(result, values[i])) < 0:
            result = tuple(-v for v in result)
        out[i] = result
        changed += distance_degrees(qs[i], result) > 1e-7
    maximum = max((distance_degrees(a, b) for a, b in zip(qs, out)), default=0.0)
    return out, {
        "changed_samples": changed,
        "max_correction_degrees": maximum,
        "protected_samples": sum(guards),
        "large_angular_steps": cuts,
        "radius_samples": radius,
        "translation_changed": False,
        "scope": "Bounded rotational filter, not support recognition or motion truth recovery.",
    }


def reconstruct_short_gap(positions, fps, start, end, leg_length, confirmed=False, cap_L=0.3):
    """Inclusive invalid sample IDs; match quadratic endpoint jets with quintic."""
    finite_positive(fps, "fps")
    finite_positive(leg_length, "leg_length")
    finite_positive(cap_L, "cap_L")
    if confirmed is not True:
        raise ValueError("Confirm this is a capture error using the source video first.")
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in (start, end)):
        raise ValueError("Gap sample IDs must be integers.")
    if start > end or start < 4 or end + 4 >= len(positions):
        raise ValueError("A short gap needs four trusted source samples on each side.")
    if (end - start + 1) / fps > 0.15 + 1e-9:
        raise ValueError("Only bracketed gaps up to 150 ms are supported; terminal tails are quarantined.")
    if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in positions):
        raise ValueError("Source positions must be finite Nx3.")
    a, z = start - 1, end + 1
    duration = (z - a) / fps

    def jet(ids, endpoint, axis):
        xs = [(i - endpoint) / fps for i in ids]
        gram = [[sum(x ** (j + k) for x in xs) for k in range(3)] for j in range(3)]
        coef = _solve(gram, [sum(positions[i][axis] * x**j for i, x in zip(ids, xs)) for j in range(3)])
        return positions[endpoint][axis], coef[1], 2 * coef[2]

    out = [tuple(p) for p in positions]
    columns = []
    for axis in range(3):
        p, v, acc = jet(range(a - 3, a + 1), a, axis)
        q, w, acl = jet(range(z, z + 4), z, axis)
        c = [p, v * duration, acc * duration**2 / 2]
        c += _solve(
            [[1, 1, 1], [3, 4, 5], [6, 12, 20]],
            [q - sum(c), w * duration - c[1] - 2 * c[2], acl * duration**2 - 2 * c[2]],
        )
        columns.append(
            [sum(co * u**k for k, co in enumerate(c)) for u in [(i - a) / (z - a) for i in range(start, end + 1)]]
        )
    for k, i in enumerate(range(start, end + 1)):
        out[i] = tuple(columns[axis][k] for axis in range(3))
    maximum = max(math.dist(a, b) / leg_length for a, b in zip(out, positions))
    if maximum > cap_L + 1e-9:
        raise ValueError(f"Proposed root correction {maximum:.4f}L exceeds the {cap_L:.4f}L budget.")
    return out, {
        "max_root_change_L": maximum,
        "changed_sample_ids": list(range(start, end + 1)),
        "scope": "Conditional endpoint interpolation. No automatic event or missing-depth recovery.",
    }


def reduce_linear_points(points, tolerance, max_evaluations=1_000_000):
    """Keep original keys with a bounded piecewise-linear scalar error.

    Refuse to guess Bezier geometry: the Blender wrapper only calls this for
    modifier-free linear curves. Budget exhaustion preserves every input key.
    """
    if (
        not isinstance(tolerance, (int, float))
        or isinstance(tolerance, bool)
        or not math.isfinite(tolerance)
        or tolerance < 0
    ):
        raise ValueError("Curve tolerance must be finite and nonnegative.")
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("Curve keys must be finite time/value pairs.")
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError("Curve times must increase strictly.")
    n = len(points)
    if n < 3 or tolerance == 0:
        return list(range(n)), {"budget_exhausted": False, "retained_keys": n}
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    evaluations = 0
    while stack:
        a, z = stack.pop()
        if z - a < 2:
            continue
        evaluations += z - a - 1
        if evaluations > max_evaluations:
            return list(range(n)), {"budget_exhausted": True, "retained_keys": n}
        x, y = points[a]
        u, v = points[z]
        error, i = max((abs(points[j][1] - (y + (v - y) * (points[j][0] - x) / (u - x))), j) for j in range(a + 1, z))
        if error > tolerance:
            keep.add(i)
            stack.extend([(a, i), (i, z)])
    ids = sorted(keep)
    return ids, {"budget_exhausted": False, "retained_keys": len(ids)}
