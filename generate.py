import os
import asyncio
import httpx
from typing import List, Dict, Any, AsyncIterator
import segment

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen-2.5-7b-instruct"

async def generate_single_chain(
    client: httpx.AsyncClient,
    problem: str,
    temperature: float
) -> Dict[str, Any]:
    """
    Generate a single solution path/chain for a given problem.
    """
    if not OPENROUTER_API_KEY:
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
            "error": "OpenRouter API Key not set"
        }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/amruth1181/amre-engine"
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise mathematical solver. Solve the user's problem step-by-step. "
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
            OPENROUTER_URL,
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
            # Try free fallback
            payload["model"] = "qwen/qwen-2.5-7b-instruct:free"
            response = await client.post(
                OPENROUTER_URL,
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
