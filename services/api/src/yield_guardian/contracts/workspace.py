"""Your work: what one workspace (the devices attached to it) has done.

Every visitor is a separate user. A run, its events, its upload, the investigations started from
it, their work orders and audit entries belong to the workspace that made them; any other session
gets exactly what a missing ID gets (404, or 410 for an ID old enough to have expired), on every
route, the event streams included. Lists are a workspace's own. Everything in a workspace is kept
until 30 days after any of its devices last used it, then deleted together; archiving a run only
takes it out of the list.

Continue on another device: `POST /workspace/handoffs` makes a code that attaches one more device
to this workspace. It is single use, ends after 10 minutes (one live code per workspace: a new one
replaces the last) and only its SHA-256 is stored. The join link carries the code after `#`, which
browsers never send to a server, so the code is in no access log.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from yield_guardian.contracts.base import Contract, Count, InvestigationId, WorkOrderId
from yield_guardian.contracts.investigation import InvestigationStatus, InvestigationSummary
from yield_guardian.contracts.runs import (
    Dataset,
    RunAlarmId,
    RunId,
    RunSource,
    RunStatus,
    StageId,
    StageStatus,
    Station,
    UploadId,
    UploadKind,
)
from yield_guardian.contracts.session import SessionRole, WorkspaceId
from yield_guardian.contracts.wafer import WaferLabel

SessionId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    Field(
        description="A device session as the admin page names it; not a credential.",
        examples=["5d0c1b8e-3f7a-4e21-8c6d-9a0b1c2d3e4f"],
    ),
]
HandoffCode = Annotated[
    str,
    StringConstraints(min_length=12, max_length=24, pattern=r"^[0-9A-Za-z\- ]+$"),
    Field(
        description="12 characters of Crockford base 32 (60 random bits), shown in groups of "
        "four; dashes, spaces and case do not matter.",
        examples=["7K2M-QX9D-4HRT"],
    ),
]
LineView = Annotated[
    str,
    StringConstraints(max_length=300, pattern=r"^[A-Za-z0-9_=&%.:+\-]*$"),
    Field(
        description="The Line page's query string for this run (run, station, unit, wafer, lot, "
        "alarm), so reopening the run shows the same view.",
        examples=["run=run_01jaf3k9x2m4q7r8s0t1v2w3x4&station=2&unit=14"],
    ),
]
NextKind = Literal["running", "failed", "decide", "watch", "investigate", "none"]


# -- the workspace and its devices -------------------------------------------------------------


class HandoffCreated(Contract):
    code: str = Field(examples=["7K2M-QX9D-4HRT"])
    expires_at: datetime
    join_path: str = Field(
        description="Open this path on the other device (the code rides after #).",
        examples=["/join#code=7K2M-QX9D-4HRT"],
    )


class HandoffRedeem(Contract):
    code: HandoffCode


class WorkspaceDevice(Contract):
    current: bool = Field(description="The device asking.")
    role: SessionRole
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class WorkspaceSummary(Contract):
    workspace_id: WorkspaceId
    created_at: datetime
    devices: list[WorkspaceDevice] = Field(description="Most recently seen first.")
    runs: Count
    uploads: Count
    investigations: Count
    session_days: Count = Field(description="A device's session ends this long after its last use.")
    handoff_minutes: Count = Field(description="A handoff code ends this long after it is made.")


# -- runs --------------------------------------------------------------------------------------


class WorkNext(Contract):
    """What this item still needs, in one sentence written by code."""

    kind: NextKind
    text: str = Field(max_length=200, examples=["2 alarms not investigated."])


class WorkRunInvestigation(Contract):
    investigation_id: InvestigationId
    alarm_id: RunAlarmId
    title: str
    status: InvestigationStatus
    updated_at: datetime
    work_order_id: WorkOrderId | None


class WorkRun(Contract):
    run_id: RunId
    created_at: datetime
    expires_at: datetime = Field(
        description="When the run is deleted, with its workspace: 30 days after the workspace "
        "was last used (each use moves it on)."
    )
    status: RunStatus
    source: RunSource
    datasets: list[Dataset]
    title: str = Field(description="How the input was chosen (the run's origin).")
    rule: str
    filename: str | None
    seed: int | None
    upload_id: UploadId | None
    again_of: RunId | None = Field(description="The run this one repeats, if it is a repeat.")
    units: Count
    wafers: Count
    stages_total: Count
    stages_finished: Count = Field(description="Stages done, skipped or failed.")
    current_stage: StageId | None
    failed_stages: list[StageId]
    alarms: Count = Field(
        description="Listed alarms that turn a station red: what the alarms rail counts as alarms."
    )
    warnings: Count = Field(
        description="The other listed alarms (warnings, unknown wafer patterns): what the alarms "
        "rail counts as warnings."
    )
    alarms_not_listed: Count
    alarms_open: Count = Field(
        description="Listed alarms and warnings no investigation was started from."
    )
    investigations: list[WorkRunInvestigation] = Field(description="Newest first.")
    label: str | None = Field(description="The name you gave the run.")
    note: str | None
    archived: bool
    view: LineView | None
    next: WorkNext


class WorkRunPage(Contract):
    items: list[WorkRun]
    next_cursor: str | None = None
    total: Count


class WorkRunUpdate(Contract):
    """Fields left out stay as they are; null clears the name or the note."""

    label: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=2000)
    archived: bool | None = None
    view: LineView | None = None


# -- uploads and investigations ----------------------------------------------------------------


class WorkUpload(Contract):
    upload_id: UploadId
    created_at: datetime
    expires_at: datetime = Field(description="When the file is deleted, with its workspace.")
    kind: UploadKind
    filename: str
    units: Count
    wafers: Count
    lots: Count
    runnable: bool
    errors: Count
    warnings: Count
    runs: list[RunId] = Field(description="Runs started from this file, newest first.")


class WorkUploadPage(Contract):
    items: list[WorkUpload]
    next_cursor: str | None = None
    total: Count


class WorkInvestigation(Contract):
    investigation: InvestigationSummary
    run_id: RunId | None = Field(description="The run it was started from, for a run alarm.")
    alarm_id: RunAlarmId | None
    run_kept: bool = Field(description="The run can still be opened.")
    next: WorkNext


class WorkInvestigationPage(Contract):
    items: list[WorkInvestigation]
    next_cursor: str | None = None
    total: Count


# -- comparing two runs ------------------------------------------------------------------------


class RunSide(Contract):
    run_id: RunId
    title: str
    created_at: datetime
    status: RunStatus
    units: Count
    wafers: Count
    alarms: Count = Field(description="Listed alarms that turn a station red.")
    warnings: Count = Field(description="The other listed alarms.")
    alarms_not_listed: Count
    units_scored: Count = Field(description="Units with a risk result.")
    units_flagged: Count = Field(description="Units whose risk is above the threshold.")
    units_chart_alarm: Count = Field(description="Units whose T² or SPE is at the alarm level.")
    units_chart_warning: Count = Field(description="Units at the warning level.")
    wafers_classified: Count
    wafers_auto_accepted: Count
    wafers_unknown: Count
    patterns: dict[WaferLabel, Count] = Field(description="Wafers by predicted pattern.")
    lots: Count
    lots_flagged: Count
    final_test: str | None = Field(description="The final-test summary, when it ran.")


class StageCompare(Contract):
    stage: StageId
    station: Station
    a_status: StageStatus
    b_status: StageStatus
    a_alarms: Count
    b_alarms: Count
    a_warnings: Count
    b_warnings: Count


class RunComparison(Contract):
    a: RunSide
    b: RunSide
    same_input: bool = Field(description="Both runs computed exactly the same input items.")
    stages: list[StageCompare]
    changes: list[str] = Field(
        description="What differs, in sentences written by code; empty when nothing does."
    )


# -- admin -------------------------------------------------------------------------------------


class AdminSession(Contract):
    """An active device session; never its cookie value or any token."""

    session_id: SessionId
    role: SessionRole
    display_name: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    role_expires_at: datetime | None
    workspace_id: WorkspaceId | None
    devices: Count = Field(description="Sessions attached to the same workspace.")
    runs: Count
    uploads: Count
    investigations: Count
    current: bool = Field(description="The admin's own session.")


class AdminSessionPage(Contract):
    items: list[AdminSession]
    next_cursor: str | None = None
    total: Count
    workspaces: Count = Field(description="Workspaces with at least one active session.")
