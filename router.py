from dataclasses import dataclass

@dataclass
class Route:
    strategy: str
    n: int
    temperature: float

def route_problem(problem: str, mode: str = "balanced") -> Route:
    """
    Decide the solving route (greedy, self-consistency, PRM weighted) based on input mode.
    """
    # Force auto mode to mapping if given
    if mode == "fast":
        return Route(strategy="greedy", n=1, temperature=0.0)
    elif mode == "balanced":
        return Route(strategy="prm_weighted_vote", n=8, temperature=0.8) # default local test cap
    elif mode == "careful":
        return Route(strategy="prm_weighted_vote", n=16, temperature=0.8) # cap to prevent too many API calls
        
    # Auto-routing based on problem characteristics (length/complexity)
    prob_len = len(problem)
    has_latex = "$" in problem or "\\" in problem
    is_complex = any(keyword in problem.lower() for keyword in ["integral", "derivative", "prove", "matrix", "combinatorics", "probability", "quadratic"])
    
    if prob_len < 50 and not is_complex:
        # Easy
        return Route(strategy="greedy", n=1, temperature=0.0)
    elif prob_len < 150 and not has_latex:
        # Medium
        return Route(strategy="prm_weighted_vote", n=4, temperature=0.7)
    else:
        # Hard
        return Route(strategy="prm_weighted_vote", n=8, temperature=0.8)
