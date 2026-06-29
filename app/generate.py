import os
import re
import asyncio
import httpx
from typing import List, Dict, Any, AsyncIterator
from . import segment

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Gemini's OpenAI-compatible endpoint: same request/response shape as before.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = "gemini-2.5-flash"

async def generate_single_chain(
    client: httpx.AsyncClient,
    problem: str,
    temperature: float
) -> Dict[str, Any]:
    """
    Generate a single solution path/chain for a given problem.
    """
    if not GEMINI_API_KEY:
        # If API key is missing, return a canned mock response to avoid crashing
        await asyncio.sleep(0.5)
        mock_text = (
            "Step 1: Simplify the equation by removing coefficients.\n"
            "Step 2: Solve the remaining variable equation.\n"
            "Step 3: Calculate the final value which yields 5.\n"
            "Final Answer: 5"
        )
        return {
            "text": mock_text,
            "steps": segment.segment_steps(mock_text),
            "answer": "5",
            "error": "Gemini API Key not set"
        }

    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise mathematical solver. Solve the user's problem step-by-step. "
                    "Write all mathematics in LaTeX wrapped in $...$ (inline) or $$...$$ (display) "
                    "so it renders correctly; keep the Final Answer line as a plain value. "
                    "You MUST structure your response strictly as follows:\n"
                    "Step 1: <explanation and calculation>\n"
                    "Step 2: <explanation and calculation>\n"
                    "...\n"
                    "Final Answer: <exact answer value>"
                )
            },
            {"role": "user", "content": problem}
        ],
        "temperature": temperature,
        "max_tokens": 1024
    }

    try:
        response = await client.post(
            GEMINI_URL,
            json=payload,
            headers=headers,
            timeout=45.0
        )
        if response.status_code == 200:
            data = response.json()
            choice_text = data["choices"][0]["message"]["content"]
            steps = segment.segment_steps(choice_text)
            answer = segment.extract_answer(choice_text)
            return {
                "text": choice_text,
                "steps": steps,
                "answer": answer
            }
            
        # Try fallback model if the primary fails or is rate limited
        elif response.status_code == 429 or response.status_code >= 500:
            # Fall back to a lighter Gemini model if the primary is rate limited / erroring
            payload["model"] = "gemini-2.0-flash"
            response = await client.post(
                GEMINI_URL,
                json=payload,
                headers=headers,
                timeout=45.0
            )
            if response.status_code == 200:
                data = response.json()
                choice_text = data["choices"][0]["message"]["content"]
                steps = segment.segment_steps(choice_text)
                answer = segment.extract_answer(choice_text)
                return {
                    "text": choice_text,
                    "steps": steps,
                    "answer": answer
                }
                
        # Error return
        return {
            "text": f"Error: API returned status code {response.status_code}\n{response.text}",
            "steps": [],
            "answer": "Error",
            "error": f"API error: {response.status_code}"
        }
    except Exception as e:
        return {
            "text": f"Error during generation: {e}",
            "steps": [],
            "answer": "Error",
            "error": str(e)
        }

async def generate_chains(
    problem: str,
    n: int,
    temperature: float = 0.8
) -> List[Dict[str, Any]]:
    """
    Generate n reasoning chains concurrently.
    """
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [
            generate_single_chain(client, problem, temperature)
            for _ in range(n)
        ]
        results = await asyncio.gather(*tasks)
        return results

async def generate_quiz_questions(topic: str, n: int = 16) -> List[str]:
    """Over-generate candidate quiz questions for a topic (IMPLEMENTATION.md §9.3).
    The engine verifies them afterwards; here we just produce raw candidates."""
    pretty = topic.replace("_", " ")
    if not GEMINI_API_KEY:
        # deterministic mock bank so the verified-quiz path still runs offline
        bank = [
            "Solve for x: 2x + 5 = 15",
            "Solve for x: 3x - 7 = 11",
            "What is 25% of 80?",
            "Factor: x^2 + 5x + 6",
            "Solve for x: x^2 - 9 = 0",
            "A bag has 3 red and 2 blue balls. P(red)?",
            "Simplify: (2/3) + (1/6)",
            "What is the derivative of x^2?",
            "Find the area of a circle with radius 4.",
            "Solve for x: 5x = 35",
        ]
        return [bank[i % len(bank)] for i in range(n)]

    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = (
        f"Generate {n} distinct, self-contained {pretty} practice problems suitable for a "
        f"high-school student. Each must have a single unambiguous numeric or short answer. "
        f"Return ONLY the problems, one per line, no numbering, no answers."
    )
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a math problem author. Output only problems, one per line."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 1024,
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GEMINI_URL, json=payload, headers=headers, timeout=45.0)
            if response.status_code == 200:
                text = response.json()["choices"][0]["message"]["content"]
                lines = [re.sub(r"^\s*\d+[.)]\s*", "", ln).strip() for ln in text.splitlines()]
                return [ln for ln in lines if len(ln) > 8][:n]
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ quiz question generation failed: {e}")
    return []


async def explain_error(problem: str, steps: List[str], error_step_idx: int) -> str:
    """
    Query Gemini to explain why the student's step is wrong and show the correct way.
    """
    if not GEMINI_API_KEY:
        return f"Error detected at Step {error_step_idx+1}: '{steps[error_step_idx]}'. Please verify the arithmetic or algebraic operations in this step."
        
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    steps_formatted = "\n".join([f"Step {i+1}: {step}" for i, step in enumerate(steps)])
    error_step_text = steps[error_step_idx]
    
    prompt = (
        f"A student is solving this math problem: '{problem}'\n\n"
        f"Here is their step-by-step work:\n{steps_formatted}\n\n"
        f"The verifier detected a mistake at Step {error_step_idx+1}: '{error_step_text}'\n\n"
        f"Please write a tutor feedback response explaining why Step {error_step_idx+1} is incorrect, "
        f"what the mistake is, and how to correct it. Keep it brief, helpful, and show the correct final solution."
    )
    
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful and encouraging high-school math tutor."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 512
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GEMINI_URL, json=payload, headers=headers, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"Error: Gemini returned status {response.status_code}. The error is likely in Step {error_step_idx+1}."
    except Exception as e:
        return f"Could not generate tutor explanation: {e}. The verification flags Step {error_step_idx+1} as incorrect."

