from __future__ import annotations

import tempfile
from pathlib import Path

from confluence_sync_tool.cme_backend import default_cme_config_json
from confluence_sync_tool.models import DEFAULT_EXPORT_OPTIONS, Job


def temp_workspace():
    return tempfile.TemporaryDirectory()


def make_job(
    root: str | Path,
    job_id: str = "product-docs",
    include_children: bool = True,
    scope: str = "pages-with-descendants",
) -> Job:
    path = Path(root) / job_id
    path.mkdir(parents=True, exist_ok=True)
    export_options = dict(DEFAULT_EXPORT_OPTIONS)
    export_options.update(
        {
            "cme_scope": scope,
            "cme_urls": "https://company.atlassian.net/wiki/spaces/PROD/pages/123456",
            "cme_config_json": default_cme_config_json(str(path)),
        }
    )
    return Job(
        id=job_id,
        name="Product Docs",
        confluence_url="https://company.atlassian.net/wiki/spaces/PROD/pages/123456",
        target_dir=str(path),
        include_children=include_children,
        include_attachments=False,
        export_options=export_options,
    )
