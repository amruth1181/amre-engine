"""
check_prm.py — is the PRM actually scoring, or silently on the 0.5 floor?

Run this anywhere the engine runs (your laptop OR the HF Space terminal). It
walks the exact failover path the engine uses and tells you, in plain language,
whether real PRM scores are coming back.

  python scripts/check_prm.py        (from the repo root)

What it checks:
  1. Is the Colab 7B PRM configured + healthy?
  2. Can the 1.5B ONNX floor download + load from HF Hub?
  3. Do scores come back and VARY between a good step and an obviously wrong one?
     (If everything is 0.5 or all identical, the model is NOT really scoring.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("=" * 60)
    print("PRM DIAGNOSTIC")
    print("=" * 60)

    # 1) Colab 7B preferred backend
    from app.prm_scoring import ColabPRM, score_steps
    colab_url = os.environ.get("COLAB_PRM_URL", "")
    print(f"\n[1] Colab 7B PRM")
    print(f"    COLAB_PRM_URL set: {bool(colab_url)}  ({colab_url or 'not set'})")
    print(f"    healthy: {ColabPRM().healthy()}")

    # 2) local Skywork 1.5B PyTorch floor: can it download + load?
    print(f"\n[2] Skywork 1.5B PyTorch floor")
    repo = os.environ.get("PRM_MODEL_REPO", "Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B")
    print(f"    PRM_MODEL_REPO: {repo}")
    try:
        from app import prm_local
        prm_local._load_model()
        print("    ✅ model downloaded + loaded (int8-quantized on CPU)")
    except Exception as e:  # noqa: BLE001
        print(f"    ❌ could NOT load: {type(e).__name__}: {e}")
        print("       -> engine will fall back to 0.5 for every step.")
        print("       Fix: ensure torch+transformers are installed and the Space")
        print("            can reach huggingface.co (the Skywork repo is public).")

    # 3) Do scores vary between a right and a clearly-wrong step?
    print(f"\n[3] Live scoring sanity (good vs wrong step)")
    problem = "Solve for x: 2x + 5 = 15"
    steps = [
        "2x = 15 - 5 = 10",   # correct
        "x = 10 / 2 = 5",     # correct
        "x = 10 * 2 = 20",    # clearly wrong
    ]
    try:
        out = score_steps(problem, steps)
    except Exception as e:  # noqa: BLE001 — mirrors the pipeline's 0.5 fallback
        print(f"    ❌ scoring raised {type(e).__name__}: {e}")
        print("\n" + "=" * 60)
        print("❌ FAIL — scoring threw; the engine would fall back to 0.5 per step.")
        sys.exit(1)
    scores = out["scores"]
    print(f"    verifier used: {out['verifier']}")
    for i, (s, sc) in enumerate(zip(steps, scores)):
        print(f"      step {i+1}: {sc:.3f}   ({s})")

    print("\n" + "=" * 60)
    all_half = all(abs(s - 0.5) < 1e-6 for s in scores)
    all_same = len(set(round(s, 4) for s in scores)) == 1
    if all_half:
        print("❌ FAIL — every score is 0.5: PRM is on the FALLBACK, not really scoring.")
        sys.exit(1)
    elif all_same:
        print("⚠️ SUSPECT — model loaded but all steps got the same score.")
        print("   The reward extraction in app/prm_local.py may not match Skywork's format.")
        sys.exit(2)
    else:
        print("✅ PASS — PRM is producing real, varying scores.")
        print(f"   (wrong step scored {scores[-1]:.3f} vs correct {scores[0]:.3f})")


if __name__ == "__main__":
    main()
