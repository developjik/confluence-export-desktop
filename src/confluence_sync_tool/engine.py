from __future__ import annotations

from typing import Callable

from .cme_backend import CmeExportResult, cme_scope, cme_urls, run_cme_export
from .errors import AppError, classify_exception
from .hashing import tree_hash
from .models import Job, PlanItem, SyncPlan
from .storage import append_app_log, append_job_log, append_run_history
from .timeutil import now_iso, run_id
from .validation import validate_job


class SyncEngine:
    def __init__(
        self,
        progress: Callable[[str, int, int], None] | None = None,
        cme_exporter: Callable[[Job, Callable[[str, int, int], None] | None], CmeExportResult] | None = None,
    ) -> None:
        self.progress = progress
        self.cme_exporter = cme_exporter or run_cme_export

    def _progress(self, message: str, done: int = 0, total: int = 0) -> None:
        if self.progress:
            self.progress(message, done, total)

    def preview(self, job: Job) -> SyncPlan:
        validate_job(job, create_dirs=True)
        return self._cme_plan(job)

    def dry_run(self, job: Job) -> SyncPlan:
        before = tree_hash(job.workspace)
        append_app_log(f"job_id={job.id} mode=dry_run status=started")
        plan = self.preview(job)
        after = tree_hash(job.workspace)
        if before != after:
            raise AppError(
                "Validation",
                "DRY_RUN_MUTATED_WORKSPACE",
                "Dry run changed the workspace.",
                f"{before} != {after}",
                False,
            )
        append_app_log(f"job_id={job.id} mode=dry_run status=success summary={plan.summary}")
        return plan

    def apply(self, job: Job, trigger: str = "manual") -> dict:
        validate_job(job, create_dirs=True)
        rid = run_id(job.id)
        started = now_iso()
        append_job_log(job, f"run_id={rid} status=started mode=cme_apply trigger={trigger}")
        status = "success"
        result_error = None
        cme_result: CmeExportResult | None = None
        try:
            cme_result = self.cme_exporter(job, self._progress)
        except Exception as exc:
            status = "failed"
            result_error = classify_exception(exc).to_dict()
        finished = now_iso()
        stats = cme_result.stats if cme_result else {}
        summary = {
            "created": int(stats.get("exported", 0)),
            "updated": 0,
            "deleted": int(stats.get("removed", 0)),
            "skipped": int(stats.get("skipped", 0)),
            "errors": 1 if status == "failed" else int(stats.get("failed", 0)),
        }
        run = {
            "run_id": rid,
            "job_id": job.id,
            "mode": "cme_apply",
            "trigger": trigger,
            "started_at": started,
            "finished_at": finished,
            "status": status,
            "summary": summary,
            "error": result_error,
            "cme": {
                "command": cme_result.command if cme_result else cme_scope(job),
                "urls": cme_result.urls if cme_result else cme_urls(job),
                "output_path": cme_result.output_path if cme_result else str(job.workspace),
                "stats": stats,
            },
        }
        append_run_history(job, run)
        append_job_log(job, f"run_id={rid} status={status} trigger={trigger} summary={summary} error={result_error}")
        if status == "failed":
            error = result_error or {}
            raise AppError(error["category"], error["code"], error["user_message"], error["technical_message"], error["retryable"])
        return run

    def _cme_plan(self, job: Job) -> SyncPlan:
        urls = cme_urls(job)
        scope = cme_scope(job)
        local_hash = tree_hash(job.workspace)
        item = PlanItem(
            action="update",
            page_id=None,
            title="CME export",
            current_path=None,
            target_path=job.target_dir,
            local_hash=None,
            reason=f"CME {scope} job; {len(urls)} URL(s). Exact skips and cleanup are decided by CME at run time.",
            safe_to_apply=True,
        )
        return SyncPlan(
            schema_version=1,
            plan_id=f"{run_id(job.id)}-cme-plan",
            job_id=job.id,
            created_at=now_iso(),
            scope=scope,
            urls=urls,
            local_snapshot_hash=local_hash,
            summary={"create": 0, "update": 1, "skip": 0, "error": 0},
            items=[item],
            warnings=["Preview validates CME config/auth shape and target path only. CME calculates page-level changes during Export Now."],
        )
