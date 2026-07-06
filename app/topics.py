"""
Topic tagging + reading material (IMPLEMENTATION.md §3 / §9.5).
Keyword + few-shot tagging into ~20 categories (no training). Each topic maps
to a small set of curated static links plus a short grounded mini-lesson.
"""
import re
from typing import Dict, List

# ~20 categories. First match (by keyword) wins; order matters (specific first).
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "calculus_integrals": ["integral", "integrate", "antiderivative", "∫"],
    "calculus_derivatives": ["derivative", "differentiate", "d/dx", "tangent slope"],
    "calculus_limits": ["limit", "lim ", "approaches", "l'hopital", "lhopital"],
    "linear_algebra": ["matrix", "matrices", "determinant", "eigen", "vector space", "dot product"],
    "probability": ["probability", "dice", "coin", "random", "expected value", "p("],
    "statistics": ["mean", "median", "mode", "variance", "standard deviation", "distribution"],
    "combinatorics": ["combination", "permutation", "factorial", "n choose", "arrange", "ways to"],
    "number_theory": ["prime", "divisible", "gcd", "lcm", "modulo", "remainder", "congruent"],
    "quadratics": ["quadratic", "x^2", "x²", "parabola", "discriminant", "factor the"],
    "polynomials": ["polynomial", "cubic", "degree", "roots of", "synthetic division"],
    "systems_of_equations": ["system of", "simultaneous", "substitution method", "elimination method"],
    "linear_equations": ["solve for x", "linear equation", "slope", "y = mx", "isolate"],
    "inequalities": ["inequality", "greater than", "less than", "≥", "≤", "at least", "at most"],
    "exponents_logs": ["exponent", "logarithm", "log", "ln ", "power of", "exponential"],
    "trigonometry": ["sin", "cos", "tan", "angle", "triangle", "radian", "degree"],
    "geometry": ["area", "perimeter", "volume", "circle", "rectangle", "polygon", "circumference"],
    "sequences_series": ["sequence", "series", "arithmetic progression", "geometric progression", "sum of the first"],
    "fractions_ratios": ["fraction", "ratio", "proportion", "percent", "%"],
    "word_problems": ["how many", "how much", "if a", "a train", "a car", "total cost"],
    "arithmetic": ["add", "subtract", "multiply", "divide", "sum of", "product of"],
}

# Curated reading links per topic (static — no scraping).
RESOURCES: Dict[str, List[Dict[str, str]]] = {
    "calculus_integrals": [
        {"title": "Khan Academy — Integration", "url": "https://www.khanacademy.org/math/calculus-1/cs1-integrals"},
        {"title": "Paul's Online Notes — Integrals", "url": "https://tutorial.math.lamar.edu/Classes/CalcI/IntegralsIntro.aspx"},
    ],
    "calculus_derivatives": [
        {"title": "Khan Academy — Derivatives", "url": "https://www.khanacademy.org/math/calculus-1/cs1-derivatives-definition-and-basic-rules"},
        {"title": "Paul's Online Notes — Derivatives", "url": "https://tutorial.math.lamar.edu/Classes/CalcI/DerivativeIntro.aspx"},
    ],
    "probability": [
        {"title": "Khan Academy — Probability", "url": "https://www.khanacademy.org/math/statistics-probability/probability-library"},
    ],
    "quadratics": [
        {"title": "Khan Academy — Quadratics", "url": "https://www.khanacademy.org/math/algebra/x2f8bb11595b61c86:quadratic-functions-equations"},
        {"title": "Purplemath — The Quadratic Formula", "url": "https://www.purplemath.com/modules/quadform.htm"},
    ],
    "linear_equations": [
        {"title": "Khan Academy — Linear equations", "url": "https://www.khanacademy.org/math/algebra/x2f8bb11595b61c86:solving-equations-inequalities"},
    ],
}

_GENERIC_RESOURCE = [
    {"title": "Khan Academy — Math", "url": "https://www.khanacademy.org/math"},
    {"title": "Paul's Online Math Notes", "url": "https://tutorial.math.lamar.edu/"},
]

_MINI_LESSONS: Dict[str, str] = {
    "quadratics": "A quadratic has the form ax² + bx + c = 0. Solve by factoring, completing the square, or the quadratic formula x = (-b ± √(b²-4ac)) / 2a. The discriminant b²-4ac tells you how many real roots exist.",
    "linear_equations": "A linear equation isolates a variable using inverse operations: undo addition/subtraction first, then multiplication/division. Whatever you do to one side, do to the other.",
    "probability": "Probability of an event = favorable outcomes / total equally-likely outcomes. For independent events multiply; for mutually exclusive events add.",
    "calculus_derivatives": "The derivative measures instantaneous rate of change. Use the power rule (d/dx xⁿ = n·xⁿ⁻¹), product, quotient, and chain rules to differentiate.",
    "calculus_integrals": "Integration reverses differentiation and measures accumulated area. Use the power rule for antiderivatives and add a constant C for indefinite integrals.",
}


def classify_topic(problem: str) -> str:
    text = problem.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return topic
    return "general_math"


def get_resources(topic: str) -> List[Dict[str, str]]:
    return RESOURCES.get(topic, _GENERIC_RESOURCE)


def mini_lesson(topic: str) -> str:
    return _MINI_LESSONS.get(
        topic,
        "Break the problem into a sequence of small, checkable steps. Identify what is given, "
        "what is asked, and which rule connects them. Verify each step before moving on.",
    )


def pretty(topic: str) -> str:
    """Human-readable topic label."""
    return topic.replace("_", " ").title()


# ============ Topic knowledge graph (feature 1.5) ============
# Prerequisite DAG: topic -> the topics you should understand first. Arithmetic is
# the root; calculus sits at the top. Drives "fix these foundations first".
PREREQUISITES: Dict[str, List[str]] = {
    "arithmetic": [],
    "fractions_ratios": ["arithmetic"],
    "word_problems": ["arithmetic"],
    "number_theory": ["arithmetic"],
    "linear_equations": ["arithmetic", "fractions_ratios"],
    "inequalities": ["linear_equations"],
    "systems_of_equations": ["linear_equations"],
    "exponents_logs": ["arithmetic", "fractions_ratios"],
    "quadratics": ["linear_equations", "exponents_logs"],
    "polynomials": ["quadratics"],
    "geometry": ["arithmetic", "fractions_ratios"],
    "trigonometry": ["geometry", "quadratics"],
    "sequences_series": ["linear_equations", "exponents_logs"],
    "combinatorics": ["arithmetic", "fractions_ratios"],
    "probability": ["fractions_ratios", "combinatorics"],
    "statistics": ["arithmetic", "fractions_ratios"],
    "linear_algebra": ["systems_of_equations"],
    "calculus_limits": ["polynomials", "trigonometry", "exponents_logs"],
    "calculus_derivatives": ["calculus_limits"],
    "calculus_integrals": ["calculus_derivatives"],
}


def _ancestors(topic: str, seen=None) -> set:
    """All prerequisite topics (transitively) required for `topic`."""
    seen = seen if seen is not None else set()
    for p in PREREQUISITES.get(topic, []):
        if p not in seen:
            seen.add(p)
            _ancestors(p, seen)
    return seen


def recommend_foundations(weak_topics: List[str], limit: int = 5) -> List[str]:
    """Given the student's weak topics, recommend which FOUNDATIONS to fix first:
    prerequisites of their weak topics that are themselves weak (so drilling the
    hard topic isn't wasted), else the direct prerequisites to shore up the base."""
    weak = set(weak_topics)
    rec: List[str] = []
    for t in weak_topics:
        for a in _ancestors(t):
            if a in weak and a not in rec:
                rec.append(a)
    if not rec:  # no weak ancestors -> suggest direct prerequisites
        for t in weak_topics:
            for p in PREREQUISITES.get(t, []):
                if p not in rec:
                    rec.append(p)
    return rec[:limit]
