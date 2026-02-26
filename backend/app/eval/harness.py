"""Simplified evaluation harness for RAG quality assessment."""
import json
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.graphs.workflow import run_workflow
from app.db.database import AsyncSessionLocal


@dataclass
class EvalResult:
    """Result of evaluating a single question."""
    question_id: str
    category: str
    expected: str
    actual: str
    correct: bool
    groundedness: float
    keyword_hit: float
    citation_count: int
    latency_ms: int


class EvalHarness:
    """Evaluation harness for wealth advisor RAG quality."""
    
    def __init__(self, questions_file: Optional[str] = None):
        path = questions_file or str(Path(__file__).parent / "questions.json")
        with open(path) as f:
            data = json.load(f)
        self.questions = data.get("questions", [])
    
    async def run_evaluation(
        self,
        tenant_id: str,
        user_id: str,
        client_id: Optional[str] = None,
    ) -> Dict:
        """Run evaluation suite and return summary."""
        results = []
        
        async with AsyncSessionLocal() as db:
            for q in self.questions:
                result = await self._eval_one(db, q, tenant_id, user_id, client_id)
                results.append(result)
                await asyncio.sleep(0.3)
        
        return self._summarize(results)
    
    async def _eval_one(self, db, q: Dict, tenant_id: str, user_id: str, client_id: Optional[str]) -> EvalResult:
        """Evaluate a single question."""
        import uuid
        
        try:
            state = await run_workflow(
                db=db,
                tenant_id=tenant_id,
                client_id=client_id,
                user_id=user_id,
                conversation_id=str(uuid.uuid4()),
                user_query=q["question"],
            )
            
            response = state.final_response.lower()
            refused = any(p in response for p in ["don't have", "cannot provide", "unable to"])
            actual = "refuse" if refused else "answer"
            
            # Groundedness: check if response words appear in chunks
            chunk_text = " ".join(c.get("content", "") for c in state.retrieved_chunks).lower()
            words = [w for w in response.split() if len(w) > 5]
            groundedness = sum(1 for w in words if w in chunk_text) / max(len(words), 1)
            
            # Keyword hit rate
            keywords = q.get("expected_keywords", [])
            keyword_hit = sum(1 for k in keywords if k.lower() in response) / max(len(keywords), 1)
            
            return EvalResult(
                question_id=q["id"],
                category=q["category"],
                expected=q["expected_behavior"],
                actual=actual,
                correct=(actual == q["expected_behavior"]),
                groundedness=groundedness,
                keyword_hit=keyword_hit,
                citation_count=len(state.citations),
                latency_ms=state.latency_ms,
            )
        except Exception as e:
            return EvalResult(
                question_id=q["id"], category=q["category"], expected=q["expected_behavior"],
                actual="error", correct=False, groundedness=0, keyword_hit=0, citation_count=0, latency_ms=0
            )
    
    def _summarize(self, results: List[EvalResult]) -> Dict:
        """Compute summary statistics."""
        n = len(results)
        if n == 0:
            return {"total": 0}
        
        by_cat = {}
        for r in results:
            by_cat.setdefault(r.category, []).append(r)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total": n,
            "accuracy": sum(r.correct for r in results) / n,
            "avg_groundedness": sum(r.groundedness for r in results) / n,
            "avg_keyword_hit": sum(r.keyword_hit for r in results) / n,
            "avg_latency_ms": sum(r.latency_ms for r in results) / n,
            "by_category": {
                cat: {"accuracy": sum(r.correct for r in rs) / len(rs)}
                for cat, rs in by_cat.items()
            },
            "results": [
                {"id": r.question_id, "correct": r.correct, "actual": r.actual}
                for r in results
            ],
        }
    
    def save_results(self, summary: Dict, output_path: str):
        """Save results to JSON."""
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
    
    def print_report(self, summary: Dict):
        """Print evaluation report."""
        print("\n" + "=" * 50)
        print("EVALUATION REPORT")
        print("=" * 50)
        print(f"Total: {summary['total']} | Accuracy: {summary['accuracy']:.1%}")
        print(f"Groundedness: {summary['avg_groundedness']:.1%} | Latency: {summary['avg_latency_ms']:.0f}ms")
        print("\nBy Category:")
        for cat, scores in summary.get("by_category", {}).items():
            print(f"  {cat}: {scores['accuracy']:.1%}")
        print("=" * 50)
