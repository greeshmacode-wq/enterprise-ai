"""Retrieval evaluation against a golden question set - no LLM involved.

Scores full-text-only, vector-only and hybrid (RRF) ranking side by side
with Hit@K, MRR and Precision@K, so a change to chunking, embeddings or
fusion can be measured instead of eyeballed.

A chunk counts as relevant when its document title contains
`expected_document` and (if given) its content contains `expected_text`,
both case-insensitive. Matching on title/text rather than chunk ids keeps
the golden file valid after documents are re-chunked or re-uploaded.

Usage:
    python manage.py evaluate_retrieval
    python manage.py evaluate_retrieval --k 10 --username alice --verbose
    
| Metric      | Question                                    |
| ----------- | ------------------------------------------- |
| Hit@K       | Did we find at least one relevant chunk?    |
| MRR         | How high was the first relevant chunk?      |
| Precision@K | How many of the top K chunks were relevant? |

"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError

from apps.accounts.models import User
from apps.search.services import rrf_fuse, text_ranked_ids, vector_ranked_ids, visible_chunks

logger = logging.getLogger(__name__)

DEFAULT_GOLDEN_PATH = Path(__file__).resolve().parents[2] / "eval" / "retrieval_golden.json"  # Line 37: DEFAULT_GOLDEN_PATH = ... / "eval" / "retrieval_golden.json" — the questions live in that JSON file, loaded at runtime (_load_golden, line 119-132). You can also point to a different file with --golden <path>.Each entry in that JSON is just {"question": ..., "expected_document": ..., "expected_text": ...}
METHODS = ("text", "vector", "hybrid")


@dataclass
class MethodScores:
    hits: list[float] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)
    precisions: list[float] = field(default_factory=list)

    def add(self, ranked_ids: list[int], relevant_ids: set[int], k: int) -> int | None:
        """Record one question's scores; returns the 1-based rank of the
        first relevant chunk, or None if none made the top k."""
        first_rank = next(
            (rank for rank, chunk_id in enumerate(ranked_ids, start=1) if chunk_id in relevant_ids),
            None,
        )
        self.hits.append(1.0 if first_rank else 0.0)
        self.reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
        self.precisions.append(sum(chunk_id in relevant_ids for chunk_id in ranked_ids) / k)
        return first_rank

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def summary(self) -> tuple[float, float, float]:
        return self._mean(self.hits), self._mean(self.reciprocal_ranks), self._mean(self.precisions)


class Command(BaseCommand):
    help = "Evaluate text / vector / hybrid retrieval against a golden question set."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
        parser.add_argument("--k", type=int, default=5, help="Cut-off rank for all metrics.")
        parser.add_argument(
            "--username",
            help="Evaluate as this user (tests RBAC scoping). Defaults to an admin, who sees every document.",
        )
        parser.add_argument("--verbose", action="store_true", help="Print per-question ranks.")

    def handle(self, *args, **options) -> None:
        k: int = options["k"]
        if k < 1:
            raise CommandError("--k must be at least 1.")

        golden = self._load_golden(options["golden"])
        user = self._resolve_user(options["username"])
        visible = visible_chunks(user)
        scores = {method: MethodScores() for method in METHODS}
        skipped = 0

        for item in golden:
            question = item["question"]
            try:
                text_ids = text_ranked_ids(question, visible)
                vector_ids = vector_ranked_ids(question, visible)
                fused = rrf_fuse([text_ids, vector_ids])
                rankings = {
                    "text": text_ids[:k],
                    "vector": vector_ids[:k],
                    "hybrid": sorted(fused, key=fused.get, reverse=True)[:k],
                }
                relevant_ids = self._relevant_ids(visible, rankings, item)
            except DatabaseError:
                logger.exception("Retrieval failed for golden question %r", question)
                self.stderr.write(self.style.WARNING(f"Skipped (DB error): {question}"))
                skipped += 1
                continue

            ranks = {
                method: scores[method].add(ranked_ids, relevant_ids, k)
                for method, ranked_ids in rankings.items()
            }
            if options["verbose"]:
                rank_text = "  ".join(f"{m}={ranks[m] or '-'}" for m in METHODS)
                self.stdout.write(f"{rank_text}  | {question}")

        self._print_report(scores, k, evaluated=len(golden) - skipped, user=user)

    @staticmethod
    def _load_golden(path: Path) -> list[dict]:
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommandError(f"Golden file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"Golden file is not valid JSON: {exc}") from exc

        if not isinstance(items, list) or not items:
            raise CommandError("Golden file must be a non-empty JSON list.")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("question") or not item.get("expected_document"):
                raise CommandError(f"Golden item #{index} needs 'question' and 'expected_document'.")
        return items

    @staticmethod
    def _resolve_user(username: str | None) -> User:
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"No user named {username!r}.") from exc
        admin = User.objects.filter(role=User.RoleChoices.ADMIN).first()
        if admin is None:
            raise CommandError("No admin user found - pass --username.")
        return admin

    @staticmethod
    def _relevant_ids(visible, rankings: dict[str, list[int]], item: dict) -> set[int]:
        """One query per question: which of the retrieved chunks are relevant."""
        candidate_ids = {chunk_id for ranked_ids in rankings.values() for chunk_id in ranked_ids}
        matches = visible.filter(
            id__in=candidate_ids, document__title__icontains=item["expected_document"]
        )
        if item.get("expected_text"):
            matches = matches.filter(content__icontains=item["expected_text"])
        return set(matches.values_list("id", flat=True))

    def _print_report(self, scores: dict[str, MethodScores], k: int, evaluated: int, user: User) -> None:
        self.stdout.write("")
        self.stdout.write(f"Evaluated {evaluated} question(s) as {user.username} ({user.role}), K={k}")
        self.stdout.write(f"{'method':<8} {'Hit@K':>7} {'MRR':>7} {'P@K':>7}")
        for method in METHODS:
            hit_rate, mrr, precision = scores[method].summary()
            self.stdout.write(f"{method:<8} {hit_rate:>7.3f} {mrr:>7.3f} {precision:>7.3f}")
