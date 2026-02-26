#!/usr/bin/env python3
"""Script to run evaluation suite."""
import asyncio
import argparse
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.eval.harness import EvalHarness


async def main():
    parser = argparse.ArgumentParser(description="Run RAG evaluation suite")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--user-id", required=True, help="User UUID")
    parser.add_argument("--client-id", help="Optional client UUID filter")
    parser.add_argument("--questions", help="Path to custom questions JSON file")
    parser.add_argument("--output", default="eval_results.json", help="Output file path")
    
    args = parser.parse_args()
    
    # Initialize harness
    harness = EvalHarness(questions_file=args.questions)
    
    print(f"Running evaluation with {len(harness.questions)} questions...")
    
    # Run evaluation
    summary = await harness.run_evaluation(
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        client_id=args.client_id,
    )
    
    # Print report
    harness.print_report(summary)
    
    # Save results
    harness.save_results(summary, args.output)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
