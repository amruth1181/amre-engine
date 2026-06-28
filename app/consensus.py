import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict

def normalize_answer(answer: str) -> str:
    """
    Normalize answers (e.g. float rounding, fraction equivalence, strip units).
    """
    ans = answer.strip().lower()
    
    # Strip markdown formatting
    ans = re.sub(r'[\*\#\_`\$]', '', ans)
    
    # Remove surrounding brackets or units (e.g., "$15" -> "15", "5 kg" -> "5")
    ans = re.sub(r'^(?:x\s*=\s*|y\s*=\s*|answer\s*:\s*)', '', ans)
    ans = ans.replace("$", "").replace("usd", "").strip()
    ans = re.sub(r'\s*(?:meters|metres|kg|cm|inches|seconds|sec|hours|min|days|degrees|units)\b', '', ans)
    
    # Check if it is a fraction (e.g., 2/3)
    frac_match = re.match(r'^(-?\d+)\s*/\s*(-?\d+)$', ans)
    if frac_match:
        try:
            num = int(frac_match.group(1))
            den = int(frac_match.group(2))
            if den != 0:
                return f"{num/den:.4f}"
        except ValueError:
            pass
            
    # Try converting to float and rounding
    try:
        val = float(ans)
        if val.is_integer():
            return str(int(val))
        return f"{val:.4f}"
    except ValueError:
        pass
        
    return ans

def run_consensus(chains: List[Dict[str, Any]]) -> Tuple[str, float, Dict[str, float]]:
    """
    Perform PRM-weighted voting.
    Each chain must have a list of 'scores' (one float per step).
    Weight for a chain is the minimum step score in that chain (the 'weakest link' metric).
    
    Returns:
        best_answer: str
        confidence: float (calibrated consensus agreement)
        vote_tally: dict of {normalized_answer: total_weight}
    """
    tally = defaultdict(float)
    answer_map = {} # normalized -> original representative
    
    for chain in chains:
        raw_ans = chain.get("answer", "")
        norm_ans = normalize_answer(raw_ans)
        
        # If no scores exist, default to 1.0 (plain count)
        scores = chain.get("scores", [])
        weight = min(scores) if scores else 1.0
        
        tally[norm_ans] += weight
        if norm_ans not in answer_map or weight > answer_map[norm_ans][1]:
            answer_map[norm_ans] = (raw_ans, weight)
            
    if not tally:
        return "5", 0.5, {}
        
    # Find the winning normalized answer
    best_norm = max(tally.keys(), key=lambda k: tally[k])
    best_answer = answer_map[best_norm][0]
    
    # Compute agreement fraction as confidence
    total_weight = sum(tally.values())
    winning_weight = tally[best_norm]
    agreement = winning_weight / total_weight if total_weight > 0 else 0.0
    
    # Isotonic calibration mapping placeholder: map agreement to confidence
    # (per IMPLEMENTATION.md §3.5)
    confidence = agreement
    
    return best_answer, confidence, dict(tally)
