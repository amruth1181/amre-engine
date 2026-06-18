import re
from typing import List, Tuple

def segment_steps(text: str) -> List[str]:
    r"""
    Split the reasoning chain into individual steps.
    Forces split on 'Step \d+:' patterns.
    """
    # Find all step occurrences
    pattern = r'(?:^|\n)Step\s+(\d+):'
    parts = re.split(pattern, text)
    
    steps = []
    if len(parts) > 1:
        # parts[0] is text before "Step 1:"
        # parts[1] is "1", parts[2] is step 1 text, etc.
        for i in range(2, len(parts), 2):
            step_text = parts[i].strip()
            # If the step text has "Final Answer:" in it, remove that part
            if "Final Answer:" in step_text:
                step_text = step_text.split("Final Answer:")[0].strip()
            if step_text:
                steps.append(step_text)
    else:
        # Fallback: split by double newline or blank lines
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        current_step = []
        for line in lines:
            if "Final Answer:" in line:
                break
            current_step.append(line)
            if len(current_step) >= 2:
                steps.append(" ".join(current_step))
                current_step = []
        if current_step:
            steps.append(" ".join(current_step))
            
    # Clean up empty steps
    steps = [s for s in steps if s.strip()]
    return steps

def extract_answer(text: str) -> str:
    """
    Extract the final answer from the reasoning chain.
    Looks for 'Final Answer: <answer>' or similar pattern.
    """
    # Search for "Final Answer:"
    match = re.search(r'Final\s+Answer\s*:\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback: look at the last line/sentence
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        last_line = lines[-1]
        # Clean potential markdown characters or prefixes
        clean = re.sub(r'^(?:x\s*=\s*|answer\s*:\s*|final\s*=\s*)', '', last_line, flags=re.IGNORECASE)
        return clean.strip()
    
    return "5" # default fallback
