"""Test fixtures for Modern Robotics textbook.

Structured plan data and chapter checklists for evaluating
teaching coverage in Professor tests.
"""

MODERN_ROBOTICS_PLAN_DATA = {
    "total_days": 30,
    "days": [
        {
            "day": 1,
            "day_title": "Introduction to Modern Robotics",
            "items": [{
                "chapter_number": 2,
                "chapter_title": "Configuration Space",
                "topics": [
                    {"name": "Degrees of Freedom", "key_formulas": ["DOF = sum(f_i) - constraints"], "priority": "core"},
                    {"name": "Configuration Space Topology", "key_formulas": [], "priority": "core"},
                    {"name": "C-space Representation", "key_formulas": [], "priority": "core"},
                ]
            }]
        },
        {
            "day": 5,
            "day_title": "Rigid-Body Motions I",
            "items": [{
                "chapter_number": 3,
                "chapter_title": "Rigid-Body Motions",
                "topics": [
                    {"name": "Rotation Matrices", "key_formulas": ["R ∈ SO(3)", "R^T R = I", "det(R) = 1"], "priority": "core"},
                    {"name": "Angular Velocities", "key_formulas": ["[ω] skew-symmetric", "ω ∈ R^3"], "priority": "core"},
                    {"name": "Exponential Coordinates", "key_formulas": ["e^{[ω]θ} = I + sin(θ)[ω] + (1-cos(θ))[ω]^2"], "priority": "core"},
                ]
            }]
        },
        {
            "day": 7,
            "day_title": "Review Day",
            "rest": True,
            "items": [],
        },
        {
            "day": 10,
            "day_title": "Forward Kinematics",
            "items": [{
                "chapter_number": 4,
                "chapter_title": "Forward Kinematics",
                "topics": [
                    {"name": "Product of Exponentials", "key_formulas": ["T(θ) = e^{[S1]θ1} ... e^{[Sn]θn} M"], "priority": "core"},
                    {"name": "DH Parameters", "key_formulas": ["a_i, alpha_i, d_i, theta_i"], "priority": "core"},
                ]
            }]
        },
    ]
}

CRITICAL_FORMULAS = {
    "chapter_3": [
        "R ∈ SO(3)",
        "Rodrigues' formula",
        "Homogeneous transformation matrix T ∈ SE(3)",
    ],
    "chapter_4": [
        "Forward kinematics: T(θ) = e^{[S1]θ1} ... e^{[Sn]θn} M",
        "Product of Exponentials formula",
    ],
    "chapter_5": [
        "Jacobian: V = J(θ)θ̇",
        "Space Jacobian vs Body Jacobian",
    ],
    "chapter_8": [
        "Newton-Euler equations: F = ma, τ = Iα",
        "Lagrangian: L = K - P",
        "τ = M(θ)θ̈ + c(θ,θ̇) + g(θ)",
    ],
}

CHAPTER_2_CHECKLIST = {
    "chapter": 2,
    "title": "Configuration Space",
    "concepts": [
        {"name": "Degrees of Freedom", "type": "definition",
         "must_mention": ["number of independent parameters", "rigid body in 3D has 6 DOF"]},
        {"name": "Grübler's Formula", "type": "formula",
         "formula": "DOF = m(N-1) - sum(c_i)",
         "must_mention": ["number of links", "number of joints", "constraints"]},
        {"name": "Configuration Space", "type": "definition",
         "must_mention": ["set of all possible configurations", "n-dimensional space"]},
        {"name": "C-space Topology", "type": "concept",
         "must_mention": ["S^1 for revolute joint", "R^1 for prismatic", "torus T^n"]},
        {"name": "Task Space vs C-space", "type": "concept",
         "must_mention": ["workspace", "end-effector", "not same as C-space"]},
    ]
}

CHAPTER_3_CHECKLIST = {
    "chapter": 3,
    "title": "Rigid-Body Motions",
    "concepts": [
        {"name": "Rotation Matrices", "type": "definition",
         "must_mention": ["3x3 matrix", "orthogonal", "determinant 1"]},
        {"name": "SO(3)", "type": "definition",
         "formula": "SO(3) = {R ∈ R^{3x3} : R^T R = I, det R = 1}",
         "must_mention": ["special orthogonal group", "set of all rotation matrices"]},
        {"name": "Uses of Rotation Matrices", "type": "concept",
         "must_mention": ["represent orientation", "change reference frame", "rotate vector"]},
        {"name": "Angular Velocity", "type": "definition",
         "formula": "ω ∈ R^3, [ω] ∈ so(3)",
         "must_mention": ["skew-symmetric", "3x3 matrix", "angular velocity vector"]},
        {"name": "Exponential Coordinates", "type": "theorem",
         "formula": "e^{[ω]θ} = I + sin(θ)[ω] + (1-cos(θ))[ω]^2",
         "must_mention": ["Rodrigues", "rotation axis", "rotation angle"]},
        {"name": "Homogeneous Transformation Matrix", "type": "definition",
         "formula": "T = [[R, p], [0, 1]] ∈ SE(3)",
         "must_mention": ["4x4 matrix", "rotation and translation", "SE(3)"]},
        {"name": "Screw Motions", "type": "theorem",
         "must_mention": ["Chasles' theorem", "rotation about axis + translation along axis", "screw axis"]},
        {"name": "Twists", "type": "definition",
         "formula": "V = (ω, v) ∈ R^6",
         "must_mention": ["6-vector", "spatial velocity", "body velocity"]},
        {"name": "Adjoint Representation", "type": "formula",
         "formula": "[Ad_T]",
         "must_mention": ["change of frame for twists", "6x6 matrix"]},
    ]
}

CHAPTER_4_CHECKLIST = {
    "chapter": 4,
    "title": "Forward Kinematics",
    "concepts": [
        {"name": "Product of Exponentials (Space Frame)", "type": "formula",
         "formula": "T(θ) = e^{[S1]θ1} e^{[S2]θ2} ... e^{[Sn]θn} M",
         "must_mention": ["screw axes", "home configuration M", "joint variables"]},
        {"name": "Product of Exponentials (Body Frame)", "type": "formula",
         "formula": "T(θ) = M e^{[B1]θ1} e^{[B2]θ2} ... e^{[Bn]θn}",
         "must_mention": ["body frame screws", "post-multiply"]},
        {"name": "Denavit-Hartenberg Parameters", "type": "method",
         "must_mention": ["four parameters per joint", "a_i, alpha_i, d_i, theta_i", "link frames"]},
        {"name": "Forward Kinematics Examples", "type": "application",
         "must_mention": ["specific robot", "calculate end-effector position"]},
    ]
}

CHAPTER_5_CHECKLIST = {
    "chapter": 5,
    "title": "Velocity Kinematics and Statics",
    "concepts": [
        {"name": "Space Jacobian", "type": "formula",
         "formula": "V_s = J_s(θ) * θ_dot",
         "must_mention": ["6xn matrix", "maps joint velocities to spatial twist"]},
        {"name": "Body Jacobian", "type": "formula",
         "formula": "V_b = J_b(θ) * θ_dot",
         "must_mention": ["body frame twist"]},
        {"name": "Singularities", "type": "concept",
         "must_mention": ["rank deficiency", "lost DOF", "determinant zero"]},
        {"name": "Manipulability", "type": "concept",
         "must_mention": ["manipulability ellipsoid", "sqrt(det(J J^T))"]},
        {"name": "Statics", "type": "formula",
         "formula": "τ = J^T F",
         "must_mention": ["joint torques", "end-effector wrench"]},
    ]
}

CHAPTER_8_CHECKLIST = {
    "chapter": 8,
    "title": "Dynamics of Open Chains",
    "concepts": [
        {"name": "Lagrangian Formulation", "type": "method",
         "formula": "L = K - P, d/dt(∂L/∂θ_dot) - ∂L/∂θ = τ",
         "must_mention": ["kinetic energy", "potential energy", "Euler-Lagrange"]},
        {"name": "Mass Matrix", "type": "formula",
         "formula": "τ = M(θ)θ̈ + c(θ,θ̇) + g(θ)",
         "must_mention": ["inertia matrix", "Coriolis", "gravity terms"]},
        {"name": "Newton-Euler Algorithm", "type": "method",
         "must_mention": ["forward recursion", "backward recursion", "inverse dynamics"]},
        {"name": "Forward Dynamics", "type": "concept",
         "must_mention": ["given torques, find accelerations", "θ̈ = M^{-1}(τ - c - g)"]},
    ]
}
