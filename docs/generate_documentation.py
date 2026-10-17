#!/usr/bin/env python3
"""Build technical + functional documentation for the Project Management app.

Field tables are read from the DocType JSON files so they cannot drift from the
schema. Prose is authored here. Outputs: DOCX (python-docx) and PDF (wkhtmltopdf).

Run with any Python that has python-docx installed, e.g. the bench venv:
    env/bin/python apps/project_management/docs/generate_documentation.py
"""

import html
import json
import os
import re
import subprocess
import tempfile

OUT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(OUT), "project_management")

M1 = "project_management_for_lands_constructions_etc"
M2 = "project_masters"

PATHS = {
	"Task Master": f"{APP}/{M2}/doctype/task_master/task_master.json",
	"Type of Work Masters": f"{APP}/{M2}/doctype/type_of_work_masters/type_of_work_masters.json",
	"Project Master Template": f"{APP}/{M2}/doctype/project_master_template/project_master_template.json",
	"Project Task Detail": f"{APP}/{M2}/doctype/project_task_detail/project_task_detail.json",
	"Project Execution": f"{APP}/{M1}/doctype/project_execution/project_execution.json",
	"Project Task Instance": f"{APP}/{M1}/doctype/project_task_instance/project_task_instance.json",
	"Task Remarks History": f"{APP}/{M1}/doctype/task_remarks_history/task_remarks_history.json",
	"Project Tracker": f"{APP}/{M1}/doctype/project_tracker/project_tracker.json",
	"WhatsApp Reminder Log": f"{APP}/{M1}/doctype/whatsapp_reminder_log/whatsapp_reminder_log.json",
	"WhatsApp Status Recipient": f"{APP}/{M1}/doctype/whatsapp_status_recipient/whatsapp_status_recipient.json",
	"Project Management Settings": f"{APP}/{M1}/doctype/project_management_settings/project_management_settings.json",
}

PERM_LABEL = [
	("read", "Read"),
	("write", "Write"),
	("create", "Create"),
	("delete", "Delete"),
	("submit", "Submit"),
	("cancel", "Cancel"),
	("amend", "Amend"),
	("report", "Report"),
	("export", "Export"),
	("print", "Print"),
	("email", "Email"),
	("share", "Share"),
]


def load(doctype):
	with open(PATHS[doctype]) as fh:
		return json.load(fh)


def ordered_fields(meta):
	order = meta.get("field_order") or [f["fieldname"] for f in meta.get("fields", [])]
	by_name = {f["fieldname"]: f for f in meta.get("fields", [])}
	return [by_name[n] for n in order if n in by_name]


def field_rows(doctype):
	"""Rows for the field table: ('section', label) or ('field', [cells])."""
	meta = load(doctype)
	rows = []
	for f in ordered_fields(meta):
		ft = f.get("fieldtype")
		if ft == "Column Break":
			continue
		if ft == "Section Break":
			# An unlabelled section break is pure layout, not a documented grouping.
			if f.get("label"):
				rows.append(("section", f["label"]))
			continue

		flags = []
		for key, label in (
			("reqd", "Mandatory"),
			("read_only", "Read-only"),
			("unique", "Unique"),
			("set_only_once", "Set once"),
			("hidden", "Hidden"),
			("allow_on_submit", "Editable after submit"),
			("in_list_view", "List view"),
			("in_standard_filter", "Standard filter"),
		):
			if f.get(key):
				flags.append(label)

		notes = []
		if f.get("fetch_from"):
			notes.append(f"Fetched from `{f['fetch_from']}`.")
		if f.get("depends_on"):
			notes.append(f"Shown when `{f['depends_on']}`.")
		if f.get("description"):
			notes.append(f["description"])

		options = f.get("options") or ""
		if ft in ("Link", "Table"):
			target = options.strip()
		elif ft == "Select":
			target = " / ".join(
				o.strip() or "(blank)" for o in options.split("\n")
			)
		else:
			target = options.strip()

		default = f.get("default")
		default = "" if default is None else str(default)

		rows.append(
			(
				"field",
				[
					f"`{f['fieldname']}`",
					f.get("label") or "",
					ft,
					target,
					default,
					", ".join(flags),
					" ".join(notes),
				],
			)
		)
	return rows


FIELD_HEADERS = ["Fieldname", "Label", "Type", "Options / Target", "Default", "Properties", "Notes"]


def perm_rows(doctype):
	meta = load(doctype)
	rows = []
	for p in meta.get("permissions", []):
		granted = [label for key, label in PERM_LABEL if p.get(key)]
		rows.append([p.get("role", ""), ", ".join(granted) or "—"])
	return rows


def props(doctype):
	"""Key document properties as bullet strings."""
	m = load(doctype)
	out = []
	out.append(f"Module: **{m.get('module')}**")
	if m.get("issingle"):
		out.append("Single DocType: one global record, no list view")
	if m.get("istable"):
		out.append("Child table: rows exist only inside a parent document")
	if m.get("is_submittable"):
		out.append("Submittable: draft (0) → submitted (1) → cancelled (2)")
	if m.get("autoname"):
		series = ""
		for f in m.get("fields", []):
			if f.get("fieldname") == "naming_series":
				series = (f.get("options") or "").strip()
		if m["autoname"] == "naming_series:":
			out.append(f"Naming: naming series `{series}`")
		elif m["autoname"].startswith("field:"):
			out.append(f"Naming: value of `{m['autoname'][6:]}` (document name = that value)")
		else:
			out.append(f"Naming: `{m['autoname']}`")
	if m.get("title_field"):
		out.append(f"Title field: `{m['title_field']}`")
	out.append(f"Rename allowed: {'yes' if m.get('allow_rename') else 'no'}")
	out.append(f"Change tracking (audit trail of field edits): {'on' if m.get('track_changes') else 'off'}")
	if m.get("links"):
		for lnk in m["links"]:
			out.append(
				f"Dashboard link: **{lnk['link_doctype']}** via `{lnk['link_fieldname']}`"
			)
	return out


# ---------------------------------------------------------------- content ----

B = []  # document blocks


def h1(t):
	B.append(("h1", t))


def h2(t):
	B.append(("h2", t))


def h3(t):
	B.append(("h3", t))


def p(t):
	B.append(("p", t))


def ul(items):
	B.append(("ul", items))


def ol(items):
	B.append(("ol", items))


def table(headers, rows, widths=None):
	B.append(("table", (headers, rows, widths)))


def ftable(doctype):
	B.append(("ftable", (FIELD_HEADERS, field_rows(doctype))))


def perms(doctype):
	rows = perm_rows(doctype)
	if not rows:
		p("No permission rules of its own: access is inherited from the parent document.")
		return
	table(["Role", "Granted"], rows, [22, 78])


def code(t):
	B.append(("code", t.strip("\n")))


def note(t):
	B.append(("note", t))


# ============================================================== front matter
h1("Project Management for Lands, Constructions etc.")
p(
	"**Technical and Functional Documentation** — Frappe/ERPNext v16 custom application "
	"`project_management`, installed on site `asset.localhost`."
)

table(
	["Item", "Value"],
	[
		["App name", "`project_management`"],
		["App title", "Project Management for lands constructions etc"],
		["Publisher", "Prajwal k"],
		["License", "MIT"],
		["Framework", "Frappe v16 (bench app, Python controllers + Desk client scripts)"],
		["Modules", "Project Masters; Project Management for lands constructions etc"],
		["External dependency", "`frappe_whatsapp` (WhatsApp Message / WhatsApp Account)"],
		["Document count", "11 DocTypes (8 standard, 1 single, 3 child tables)"],
		["Document date", "15 October 2026"],
	],
	[26, 74],
)

h2("Contents")
table(
	["Section", "Subject"],
	[
		["1. Purpose and scope", "What the app does and what this document covers"],
		["2. System overview", "Masters vs. execution layers, data model map, naming series"],
		["3. Roles and authorisation model", "Roles, row-level permission hooks, user-to-employee mapping"],
		["4. Functional walkthrough", "End-to-end business flow, configuration to completion"],
		[
			"5. DocType reference",
			"5.1 Task Master · 5.2 Type of Work Masters · 5.3 Project Master Template · "
			"5.4 Project Task Detail · 5.5 Project Execution · 5.6 Project Task Instance · "
			"5.7 Task Remarks History · 5.8 Project Tracker · 5.9 WhatsApp Reminder Log · "
			"5.10 WhatsApp Status Recipient · 5.11 Project Management Settings",
		],
		["6. Reminder engine", "Scheduling, dispatch re-checks, interval arithmetic"],
		["7. WhatsApp messaging", "The three outbound kinds and link rewriting"],
		["8. Whitelisted API surface", "Every server endpoint and its guard"],
		["9. Hooks, migrations and installation", "hooks.py, the five patches, install commands"],
		["10. Data lifecycle and deletion rules", "What each action creates, updates or removes"],
		["11. Configuration checklist", "Ordered setup steps for a new installation"],
		["12. Troubleshooting", "Error messages and their causes"],
		["13. Source map", "Where each behaviour lives in the repository"],
	],
	[26, 74],
)

h2("1. Purpose and scope")
p(
	"The application turns repeatable project playbooks into tracked, reminder-driven "
	"execution for an owner running several lines of business (land, construction, trading). "
	"An administrator configures reusable masters once; an employee then only picks a project "
	"template, names the project, selects a task, types remarks and chooses a status."
)
p("This document covers, for every DocType in the app:")
ul(
	[
		"what it is for in business terms (functional view);",
		"every field with type, target DocType, default and behavioural flags (technical view);",
		"server-side controller logic, validations and derived values;",
		"the role permission matrix as shipped;",
		"how it connects to the rest of the data model.",
	]
)
p(
	"It also documents the reminder scheduler, the WhatsApp delivery layer, the whitelisted "
	"API surface, hooks, migration patches and operational configuration."
)

h2("2. System overview")

h3("2.1 Two layers: masters and live execution")
p(
	"The data model separates **configuration** from **execution**. Project Masters holds "
	"reusable definitions; the execution module holds one independent copy per live project, "
	"so two projects built from the same template never share status, assignees, due dates, "
	"remarks or reminder state."
)

table(
	["Layer", "DocTypes", "Who maintains it"],
	[
		[
			"Masters (configuration)",
			"Task Master, Type of Work Masters, Project Master Template, Project Task Detail",
			"Admin Master / System Manager",
		],
		[
			"Execution (live data)",
			"Project Execution, Project Task Instance, Task Remarks History, Project Tracker",
			"Created by the system; updated by Concern Persons",
		],
		[
			"Messaging and configuration",
			"WhatsApp Reminder Log, WhatsApp Status Recipient, Project Management Settings",
			"Scheduler writes logs; settings are administrator-owned",
		],
	],
	[24, 48, 28],
)

h3("2.2 Data model map")
code(
	"""
Type of Work Masters ──┐
                       ├─> Project Master Template (submittable)
Task Master ───────────┘        │  task_details (child: Project Task Detail)
     │                          │
     │                          v
     │               Project Execution  (PM-PRJ-#####)   live project
     │                          │  after_insert: one task instance per template row
     │                          v
     └──────────────> Project Task Instance (PM-TASK-#####)
                                │  remarks_history (child: Task Remarks History)
                                ^
                                │  appends one row per save
                     Project Tracker  (PM-TRK-####)   employee entry screen
                                │  owns exactly one Project Execution (unique)
                                v
                     WhatsApp Reminder Log (PM-WA-#####)  every outbound attempt
                     Project Management Settings (single)  switches + recipients
"""
)

h3("2.3 Naming series")
table(
	["DocType", "Series / naming rule"],
	[
		["Task Master", "`TASK-.####`"],
		["Type of Work Masters", "`WORK-.####`"],
		["Project Master Template", "named by `project_name` (unique business name)"],
		["Project Execution", "`PM-PRJ-.#####`"],
		["Project Task Instance", "`PM-TASK-.#####`"],
		["Project Tracker", "`PM-TRK-.####`"],
		["WhatsApp Reminder Log", "`PM-WA-.#####`"],
		["Project Management Settings", "single document, no series"],
		["Project Task Detail / Task Remarks History / WhatsApp Status Recipient", "child rows, hashed names"],
	],
	[40, 60],
)

h2("3. Roles and authorisation model")
p(
	"Three roles are relevant. `Admin Master` and `Concern Person` are created by the app's "
	"`after_install` / `after_migrate` hook (`project_management.install.after_install`); "
	"`System Manager` is a framework role."
)
table(
	["Role", "Intent", "Effective reach"],
	[
		[
			"System Manager",
			"Technical administrator",
			"Everything, including deleting projects and logs",
		],
		[
			"Admin Master",
			"Business owner / project office",
			"All masters, all projects, all tasks; may send WhatsApp status and manual reminders",
		],
		[
			"Concern Person",
			"Employee responsible for tasks",
			"Reads masters; sees and updates only task instances assigned to them; may create a tracker entry",
		],
	],
	[20, 28, 52],
)
p(
	"Row-level filtering is enforced on the server in `project_management/permissions.py`, "
	"wired through `hooks.py`:"
)
table(
	["Hook", "DocType", "Function"],
	[
		[
			"`permission_query_conditions`",
			"Project Task Instance",
			"`task_instance_query_conditions` — appends `concern_person = <employee>`; returns `1=0` when the user has no active Employee record",
		],
		[
			"`permission_query_conditions`",
			"Project Tracker",
			"`tracker_query_conditions` — own entries only",
		],
		[
			"`has_permission`",
			"Project Task Instance",
			"`has_task_instance_permission` — document-level equivalent of the query condition",
		],
		[
			"`has_permission`",
			"Project Tracker",
			"`has_tracker_permission` — allows an unsaved document (the controller fills `concern_person` during validate), then restricts to own entries",
		],
	],
	[27, 20, 53],
)
note(
	"Button visibility is never treated as authorisation. The two restricted actions "
	"(`send_status_to_admin_master`, `send_manual_task_reminder`) call "
	"`require_reminder_permission()` server-side, and `Project Tracker.validate_assignment()` "
	"re-checks task ownership on every save."
)
p(
	"A user is mapped to an Employee by `get_employee_for_user(user)`: "
	"`Employee` where `user_id = <session user>` and `status = Active`. `Administrator` is "
	"treated as elevated and maps to no Employee. Elevated roles are "
	"`('Admin Master', 'System Manager', 'Administrator')`."
)

h2("4. Functional walkthrough")
ol(
	[
		"**Define vocabulary.** Create `Task Master` records (the reusable task names) and "
		"`Type of Work Masters` records (Land, Construction, Trading…).",
		"**Build a playbook.** Create a `Project Master Template`: pick the type of work and add "
		"one task row per stage — task, concern person, completion timeline in days, reminders "
		"on/off, reminder interval in days. **Submit** it; only submitted, non-disabled templates "
		"can produce live projects.",
		"**Start a project.** The employee opens `Project Tracker`, picks the template, types the "
		"project name and optionally a start date. The template's task rows render as a read-only "
		"pipeline preview before the first save.",
		"**Report progress.** In the Entry Form, choose the task and type the remarks. The status "
		"starts at Open and the save promotes it to In Progress on its own; Completed is only "
		"reached by choosing it. The overall Project Status can be overridden on the same entry.",
		"**First save creates the live project.** The tracker creates its own `Project Execution` "
		"plus one `Project Task Instance` per template row, each with "
		"`due_date = start_date + completion_timeline_in_days` and the first reminder scheduled; then "
		"it writes the remark to the selected task. Template, project name and start date become "
		"read-only afterwards.",
		"**Every later save appends.** The remark is added to the selected task's "
		"`Task Remarks History` and never overwrites an earlier one. To report the next task of the "
		"same project, change **Task** on the same tracker entry and save again — the previous task "
		"keeps everything written on it. Re-saving with an unchanged remark and status adds nothing.",
		"**Completion.** Setting a task to Completed stamps `completed_on`, clears the reminder "
		"schedule, and refreshes the project's counters and progress percentage.",
		"**Reminders.** While a task is still Open or In Progress, the hourly scheduler sends a "
		"WhatsApp reminder to the assigned Concern Person every `reminder_in_days` days, counted "
		"from the latest remark or the last successful send.",
		"**Oversight.** Admin Master can send a project status summary to configured recipients, or a "
		"manual reminder with an extra note, from the tracker or the project.",
	]
)

h2("5. DocType reference")
p(
	"Sections 5.1 to 5.11 follow the lifecycle order: masters, template, live project, task, "
	"history, tracker, log, settings. Field tables are generated from the DocType JSON; the "
	"`Properties` column lists the framework flags actually set on the field."
)

# ---------------------------------------------------------------- 5.1 Task Master
h3("5.1 Task Master — Project Masters")
p(
	"**Functional role.** The controlled vocabulary of task names used everywhere else: template "
	"rows, live task instances and remark history all point at a Task Master record. Keeping task "
	"names here means a renamed or retired task is corrected in one place instead of in every project."
)
ul(props("Task Master"))
p("**Fields**")
ftable("Task Master")
p(
	"**Behaviour.** `task_master` (the display name) is mandatory and unique, so the same task "
	"cannot be created twice; `disabled` retires a task from new configuration without touching "
	"history. `description` is free text explaining what the task covers. Controller "
	"`task_master.py` adds no validation beyond the schema."
)
p("**Permissions**")
perms("Task Master")

# ------------------------------------------------- 5.2 Type of Work Masters
h3("5.2 Type of Work Masters — Project Masters")
p(
	"**Functional role.** Business-line classification for templates and projects — Land, "
	"Construction, Trading, and anything else the owner runs. It is the reporting dimension that "
	"lets one installation serve several businesses."
)
ul(props("Type of Work Masters"))
p("**Fields**")
ftable("Type of Work Masters")
p(
	"**Behaviour.** `work_name` is mandatory, unique and a standard filter, so list views can be "
	"sliced by business line. `Project Execution.type_of_work` is fetched from the template, which "
	"means the classification follows the project automatically and cannot be set inconsistently."
)
p("**Permissions**")
perms("Type of Work Masters")

# ------------------------------------------- 5.3 Project Master Template
h3("5.3 Project Master Template — Project Masters")
p(
	"**Functional role.** The reusable playbook: one business line plus the ordered list of tasks "
	"with who owns each, how long it should take and how often to chase it. It is submittable, "
	"because a template that live projects are built from must be frozen and auditable, not edited "
	"underneath them."
)
ul(props("Project Master Template"))
p("**Fields**")
ftable("Project Master Template")
p("**Validation (`validate_tasks`, runs on every save and before submit)**")
ul(
	[
		"At least one row in Task Details — an empty playbook would create a project with no tasks.",
		"No duplicate `task` across rows: each task may appear only once per template.",
		"`completion_timeline_in_days` must be a positive integer on every row — it is the input to every due date.",
		"When `enable_reminders` is set, `reminder_in_days` must be a positive integer.",
		"When `enable_reminders` is cleared, `reminder_in_days` is forced to 0, so a stale interval cannot survive turning reminders off.",
	]
)
p("**Actions**")
ul(
	[
		"**Create Live Project** (client button, visible only when `docstatus = 1` and not disabled) calls the "
		"whitelisted `create_project_execution(project_title, start_date)`, which re-checks submission "
		"server-side, creates a `Project Execution` carrying the template, title, type of work and start "
		"date, and routes the user to it. A project created this way has no owning tracker.",
		"Child-row client logic: toggling **Reminders** in a row sets `reminder_in_days` to 0 when switched "
		"off and defaults it to 7 when switched on.",
	]
)
p("**Permissions**")
perms("Project Master Template")

# ------------------------------------------------- 5.4 Project Task Detail
h3("5.4 Project Task Detail — Project Masters (child table)")
p(
	"**Functional role.** One planned stage inside a template: which task, who is responsible, how "
	"many calendar days it should take, and the reminder cadence. These rows are the blueprint that "
	"`Project Execution` copies into live task instances."
)
ul(props("Project Task Detail"))
p("**Fields**")
ftable("Project Task Detail")
p(
	"**Behaviour.** Row order (`idx`) is meaningful: it becomes `Project Task Instance.sequence` and "
	"therefore the display order of the pipeline. `task_name` and `employee_name` are fetched read-only "
	"copies for grid readability. `reminder_in_days` is hidden unless `enable_reminders` is on. The row "
	"is validated by the parent template, not by its own controller."
)
p("**Permissions**")
perms("Project Task Detail")

# ---------------------------------------------------- 5.5 Project Execution
h3("5.5 Project Execution — live project")
p(
	"**Functional role.** A real project under way: the site, plot or deal being executed. It is the "
	"aggregate record — progress counters, expected end date and overall status — and the parent of "
	"the live task instances. It stays a first-class DocType: it can be opened directly to review "
	"progress, and it can be created from a submitted template without any tracker."
)
ul(props("Project Execution"))
p("**Fields**")
ftable("Project Execution")
p("**Controller logic (`project_execution.py`)**")
table(
	["Hook / method", "What it does"],
	[
		["`validate`", "Defaults `start_date` to today when left empty."],
		[
			"`after_insert` → `create_task_instances`",
			"Loads the template, refuses a template that is not submitted, then inserts one "
			"`Project Task Instance` per `task_details` row — copying task, task name, `sequence = row.idx`, "
			"concern person, completion timeline, reminder switch and reminder interval — with "
			"`current_status = Open` and `activation_date = project start date`.",
		],
		[
			"`after_insert` → `update_progress`",
			"Computes the counters immediately so a new project shows its task count.",
		],
		[
			"`update_progress(status=None)`",
			"Re-reads all task instances and writes `total_tasks`, `completed_tasks`, "
			"`in_progress_tasks`, `open_tasks = total − completed − in progress`, `progress_percent` "
			"(2 decimals), `expected_end_date = max(task due dates)` and the derived `status` in a "
			"single `db_set` with `update_modified=False`, so refreshing counters does not look like "
			"a user edit.",
		],
		[
			"`derive_status(total, completed, in_progress, status)`",
			"An explicit status always wins. Otherwise the project mirrors its tasks: all tasks "
			"completed promotes to Completed, any task under way is In Progress, and a project whose "
			"tasks are all untouched is still Open. A manual On Hold or Cancelled is never overridden "
			"by progress.",
		],
		[
			"`get_pipeline()` (whitelisted)",
			"Returns the ordered stage list with status and full remark history for the form's HTML pipeline.",
		],
	],
	[27, 73],
)
p(
	"**Derived vs. entered.** Only `project_title`, `project_master`, `status` and `start_date` are "
	"entered. `type_of_work` is fetched from the template; `expected_end_date`, the four progress "
	"fields and the task pipeline are computed. `tasks_html` is a rendering target, not stored data."
)
p("**Permissions**")
perms("Project Execution")
note(
	"A Concern Person has read/report only on Project Execution. Project creation during a tracker "
	"save therefore runs with `ignore_permissions=True` on a fully constrained payload — otherwise an "
	"employee recording the first update of a project would be blocked by the project's own permissions."
)

# ------------------------------------------------- 5.6 Project Task Instance
h3("5.6 Project Task Instance — the live task")
p(
	"**Functional role.** The unit of work people actually report on: one task of one project, with "
	"its own assignee, due date, status, reminder schedule and remark history. It is the reason two "
	"projects from the same template are fully independent — each has its own instances."
)
ul(props("Project Task Instance"))
p("**Fields**")
ftable("Project Task Instance")
p("**Controller logic (`project_task_instance.py`)**")
table(
	["Method", "What it does"],
	[
		["`validate`", "Runs `set_due_date` then `sync_reminder_schedule`."],
		[
			"`set_due_date`",
			"`due_date = activation_date + completion_timeline_in_days` in calendar days, when both are present.",
		],
		[
			"`sync_reminder_schedule`",
			"Completed task: clears `next_reminder_due`, sets `reminder_state = Disabled`, stamps "
			"`completed_on` if unset. Re-opened task: clears `completed_on`. Reminders off or interval ≤ 0: "
			"clears the due slot and sets `Disabled`. Otherwise recomputes `next_reminder_due` and lifts the "
			"state from blank/`Disabled` to `Scheduled`.",
		],
		[
			"`reminder_anchor`",
			"The event the next reminder counts from: the later of `last_reminder_sent_on` and "
			"`last_remark_on`, falling back to the record's creation time.",
		],
		[
			"`compute_next_reminder_due(anchor)`",
			"`anchor + reminder_in_days`, snapped to midnight. Day granularity is deliberate: the dispatch "
			"job runs in one fixed hour, so a due slot carrying the anchor's clock time would be missed on "
			"its own day and the interval would drift by a day every cycle.",
		],
		[
			"`sync_tracker_remark(...)`",
			"Appends exactly one `Task Remarks History` row per new remark — task, remark text, status at "
			"entry, previous status, `status_changed`, entry time, concern person and name, entering user and "
			"the tracker entry it came from — then recomputes and saves. The remark is itself the evidence "
			"work has started, so `status_for_remark` promotes an Open task to In Progress here; Completed "
			"is passed through untouched and never derived. A save repeating the most recent remark *and* "
			"status returns without appending, so re-saving an unchanged form cannot pad the history. Empty "
			"remarks are rejected.",
		],
		[
			"`latest_remark` / `sorted_history`",
			"History is ordered by `entry_datetime`, then grid `idx` as tiebreaker; the latest row drives "
			"current state.",
		],
		[
			"`recompute_from_history`",
			"Derives `current_status` and `last_remark_on` from the newest history row — falling back to "
			"Open when every remark has been withdrawn, because nothing records work any more — so editing "
			"or deleting tracker entries cannot leave a stale status. A new remark on a task that is not "
			"Completed resets `reminder_state` to `Scheduled`.",
		],
		[
			"`mark_reminder_sent(sent_on)`",
			"Stamps `last_reminder_sent_on`, sets `reminder_state = Sent` and recomputes `next_reminder_due` "
			"from the later of the send and the last remark — all with `update_modified=False`.",
		],
		[
			"`remove_tracker_remark(tracker_entry)`",
			"Drops history rows written by one tracker entry and reindexes. Used by migration patches only; "
			"normal saves append the next remark instead of retracting one.",
		],
	],
	[26, 74],
)
p(
	"**Mobile number resolution.** `concern_person_mobile` is fetched from the Employee's "
	"`cell_number` but remains editable, so a task can be chased on a different number without "
	"changing the Employee master. It is the number every automatic and manual reminder uses."
)
p("**Permissions**")
perms("Project Task Instance")
note(
	"Admin Master has no `delete` on task instances; deletion happens through "
	"`Project Tracker.on_trash` (with `ignore_permissions`) or by a System Manager. Concern Person "
	"has read/write/report, narrowed to their own rows by the permission hooks."
)

# ------------------------------------------------- 5.7 Task Remarks History
h3("5.7 Task Remarks History — append-only audit trail (child table)")
p(
	"**Functional role.** The progress narrative of a task: every remark anyone wrote, when, under "
	"which status, and whether that entry changed the status. It is the evidence behind the pipeline "
	"view and the content of every reminder message."
)
ul(props("Task Remarks History"))
p("**Fields**")
ftable("Task Remarks History")
p("**Behaviour**")
ul(
	[
		"Every field is read-only in the UI: rows are written by `sync_tracker_remark`, never typed into the grid.",
		"`previous_status` and `status_changed` make a status transition visible without diffing rows.",
		"`tracker_entry` records which Project Tracker entry produced the row — the link used by migration patches and audit review.",
		"`sort_order` is DESC on creation, so the newest remark is shown first in the grid; the pipeline renderer sorts ascending by `entry_datetime` and shows the full trail.",
		"`entry_datetime` is stamped when the remark is written, not when the tracker entry was created, because reminders compare against it.",
	]
)
p("**Permissions**")
perms("Task Remarks History")

# ---------------------------------------------------- 5.8 Project Tracker
h3("5.8 Project Tracker — the employee entry screen")
p(
	"**Functional role.** The single screen an employee uses. It answers four questions — which "
	"project, which task, what happened, what is the status — and does everything else implicitly: "
	"creating the live project, resolving the task instance, appending the remark and refreshing "
	"project progress. One tracker owns exactly one project (`project` is unique)."
)
ul(props("Project Tracker"))
p("**Fields**")
ftable("Project Tracker")
p("**Controller logic (`project_tracker.py`)**")
table(
	["Hook / method", "What it does"],
	[
		[
			"`before_insert` → `create_project`",
			"Requires a template and a project name; refuses a template that is not submitted or is "
			"disabled; creates the tracker's own `Project Execution` with "
			"`start_date = start_date or today` using `ignore_permissions=True`, and stores its name in "
			"`project`. The project's `after_insert` then builds the task instances.",
		],
		[
			"`validate` → `resolve_task_instance`",
			"Maps the chosen Task Master to this project's own task instance "
			"(`project_execution = project AND task = task`) and throws when the task is not part of the "
			"project — the guard that prevents reporting on a foreign task.",
		],
		[
			"`validate` → `validate_assignment`",
			"Elevated roles pass. Otherwise the session user's active Employee must equal the task "
			"instance's `concern_person`, else `frappe.PermissionError`.",
		],
		[
			"`validate` (remaining)",
			"Stamps `entry_datetime` and `entered_by` when empty, resolves `concern_person` from the session "
			"user (falling back to the task's assignee), trims `remarks` and rejects an empty remark.",
		],
		[
			"`on_update` → `apply_to_task_instance`",
			"Runs on insert and on every edit: appends the remark to the resolved task instance with a fresh "
			"timestamp, then calls `Project Execution.update_progress(status=project_status)` so an explicit "
			"Project Status on the entry overrides the progress-derived one.",
		],
		[
			"`on_trash`",
			"Deletes the owned project: every task instance first (`force`, `delete_permanently`), then the "
			"`Project Execution`. Nothing else references them, so leaving them behind would strand a project "
			"no screen can reach or update.",
		],
		["`get_pipeline()` (whitelisted)", "Delegates to `project_management.api.get_project_pipeline`."],
	],
	[27, 73],
)
p("**Client behaviour (`project_tracker.js`)**")
ul(
	[
		"`project_template` link query is filtered to `docstatus = 1, disabled = 0`.",
		"`task` uses the server query `api.tracker_task_query`: before the live project exists options come "
		"from the template's rows, afterwards from the project's own task instances — so a task later "
		"removed from the template is still selectable on a running project. A Concern Person only ever "
		"sees their own assignments.",
		"`lock_project_fields` makes `project_template`, `project_name` and `start_date` read-only once the "
		"project exists, mirroring the `set_only_once` server rule, and clears the \"created on save\" hint "
		"that would otherwise misdescribe a saved entry.",
		"Selecting a template defaults `project_name` to the template name and renders the template preview; "
		"typing a name that already exists shows a warning that saving creates a separate project.",
		"After save the pipeline is rendered from `api.get_project_pipeline` — stages, status, due dates and "
		"the full remark trail.",
		"**Open Live Project** routes to the owned `Project Execution`. **Send Status to Admin Master** and "
		"**Send Manual Task Reminder** are rendered only after `permissions.can_manage_all_tasks` returns "
		"true, and both pass `[doctype, name]` so the message links back to the record being viewed.",
	]
)
p("**Permissions**")
perms("Project Tracker")
note(
	"Concern Person has create + read + report but no `write`: an employee files entries and reads "
	"them back, while corrections to an existing entry stay with Admin Master / System Manager. "
	"Deleting a tracker is destructive by design — it removes the project it owns."
)

# ------------------------------------------------ 5.9 WhatsApp Reminder Log
h3("5.9 WhatsApp Reminder Log — outbound audit")
p(
	"**Functional role.** One row per outbound attempt of any kind, with the exact message body, the "
	"recipient, the provider message id, the outcome and the error or skip reason. It is both the "
	"delivery audit trail and the deduplication store that stops a retried job from messaging twice."
)
ul(props("WhatsApp Reminder Log"))
p("**Fields**")
ftable("WhatsApp Reminder Log")
p("**Lifecycle (`whatsapp.py`)**")
ol(
	[
		"`send_whatsapp_message(...)` looks up any existing log with the same `idempotency_key`. A key "
		"found in state `Sent`, `Skipped` or `Queued` returns that row and sends nothing; a `Failed` row "
		"is retried **in place**, reusing the row so the unique key stays unique.",
		"Otherwise a new log row is created with `delivery_status = Queued`, the message body, recipient, "
		"triggering user and attempt time.",
		"Reminders disabled globally → `Skipped`, reason \"WhatsApp reminders are disabled in Project "
		"Management Settings\", nothing sent. No recipient number → `Skipped`, reason \"Recipient has no "
		"WhatsApp number configured\".",
		"`_dispatch` inserts an outgoing `WhatsApp Message` (frappe_whatsapp) with "
		"`reference_doctype = WhatsApp Reminder Log` and `reference_name = <log>`, then records "
		"`whatsapp_message`, `provider_message_id` and a delivery status taken **from the created "
		"document's own status** — a submitted API request is never reported as delivered. Recognised "
		"success states: `Success, sent, Sent, delivered, read, accepted`.",
		"Any exception is logged to the Error Log and stored in `error_response` as JSON with "
		"`delivery_status = Failed`, which keeps the attempt retryable.",
	]
)
p("**Idempotency key formats**")
table(
	["Kind", "Key", "Effect"],
	[
		["Automatic Reminder", "`auto::<task instance>::<YYYY-MM-DD due slot>`", "One send per task per due slot, however often the job is retried"],
		["Manual Reminder", "`manual::<task instance>::<timestamp>`", "Every manual press is a distinct, deliberate send"],
		["Status Summary", "`status::<project>::<number>::<timestamp>`", "Per recipient, per press"],
	],
	[22, 42, 36],
)
p("**Permissions**")
perms("WhatsApp Reminder Log")
note(
	"Nobody has `create` and only System Manager has `write`: rows are written by the server with "
	"`ignore_permissions` and are an audit trail, not a data-entry screen. Admin Master reads, "
	"exports and prints them."
)

# -------------------------------------------- 5.10 WhatsApp Status Recipient
h3("5.10 WhatsApp Status Recipient — child table of Settings")
p(
	"**Functional role.** The distribution list for **Send Status to Admin Master**: who receives "
	"project status summaries, on which number, and whether that entry is currently active."
)
ul(props("WhatsApp Status Recipient"))
p("**Fields**")
ftable("WhatsApp Status Recipient")
p(
	"**Behaviour.** `mobile_number` is mandatory and defaults to the Employee's `cell_number`, but "
	"stays editable so a recipient can be reached on a different number without editing the HR "
	"master. `Project Management Settings.get_status_recipients()` returns only rows with "
	"`enabled = 1` **and** a number, so clearing the checkbox pauses a recipient without losing the "
	"configuration."
)
p("**Permissions**")
perms("WhatsApp Status Recipient")

# ------------------------------------------- 5.11 Project Management Settings
h3("5.11 Project Management Settings — single DocType")
p(
	"**Functional role.** The one place that controls outbound messaging: the master switch, the "
	"dispatch hour, the fallback interval, whether completed tasks may be chased manually, the "
	"public URL used in message links, and the status distribution list."
)
ul(props("Project Management Settings"))
p("**Fields**")
ftable("Project Management Settings")
p("**Field semantics**")
table(
	["Setting", "Effect in code"],
	[
		[
			"`enable_whatsapp_reminders`",
			"Checked first by `tasks.send_due_reminders` (returns immediately when off) and again by "
			"`whatsapp.send_whatsapp_message`, which logs a `Skipped` row instead of sending. Off means no "
			"outbound message of any kind, including manual ones.",
		],
		[
			"`default_reminder_in_days`",
			"Fallback value only. The live interval is always read from the task instance, which copied it "
			"from the template row — never hardcoded, never taken from Settings at send time.",
		],
		[
			"`allow_manual_reminder_for_completed`",
			"When off (the shipped default), `api.send_manual_task_reminder` refuses a Completed task and "
			"names it in the error.",
		],
		[
			"`reminder_send_hour`",
			"The single hour of the day in which dispatch happens. The scheduler runs hourly and returns "
			"unless `now().hour` matches. Tested for \"configured\", not truthiness, so `0` (midnight) is a "
			"valid hour.",
		],
		[
			"`public_base_url`",
			"Replaces the host of every outgoing link. WhatsApp only renders a URL as a tappable link when "
			"the host looks like a real domain, so `http://127.0.0.1:8007/...` or a `localhost` address "
			"arrives as plain text. Blank means the site's own URL is used.",
		],
		[
			"`status_recipients`",
			"Rows read by `get_status_recipients()`; an empty or fully disabled list makes **Send Status to "
			"Admin Master** throw \"No Admin Master recipient configured\".",
		],
	],
	[30, 70],
)
p(
	"**Install-time defaults.** `install.ensure_settings()` sets `default_reminder_in_days = 7`, "
	"`reminder_send_hour = 9` and `enable_whatsapp_reminders = 1` on a fresh install, and runs again "
	"after every migrate (`after_migrate`), filling the values only when `default_reminder_in_days` "
	"is empty."
)
p("**Permissions**")
perms("Project Management Settings")

h2("6. Reminder engine")
h3("6.1 Schedule and selection")
p(
	"`hooks.scheduler_events` registers `project_management.tasks.send_due_reminders` on "
	"`hourly_long`. Each run:"
)
ol(
	[
		"returns immediately if `enable_whatsapp_reminders` is off;",
		"selects task instances where `current_status` is Open or In Progress, `enable_reminders = 1` "
		"and `next_reminder_due <= now`;",
		"enqueues one background job per task on the `long` queue with "
		"`job_id = pm-reminder::<task>` and `deduplicate=True`, so a user's Save is never blocked "
		"and the same task cannot be queued twice concurrently.",
	]
)
h3("6.2 Dispatch re-checks (`dispatch_reminder`)")
p("The task is reloaded immediately before sending, because the world may have moved on:")
table(
	["Condition at dispatch", "Action"],
	[
		[
			"Task has been Completed",
			"`reminder_state = Skipped`, `next_reminder_due` cleared, a `Skipped` log row written with reason "
			"\"Task is Completed; reminders apply to open work only\". Nothing sent.",
		],
		[
			"Reminders turned off or interval ≤ 0",
			"`reminder_state = Disabled`, due slot cleared, `Skipped` log row \"Reminders disabled for this task\".",
		],
		[
			"Recomputed due slot is still in the future (a newer remark or send arrived)",
			"The timer is restarted: `next_reminder_due` rewritten, `reminder_state = Scheduled`. Nothing sent.",
		],
		[
			"Otherwise",
			"Builds the body with `api.build_reminder_message(task)` and sends to "
			"`concern_person_mobile` as `Automatic Reminder`, with idempotency key "
			"`auto::<task>::<due date>`.",
		],
		[
			"Result `Sent`",
			"`mark_reminder_sent()` — stamps the send, sets state `Sent`, schedules the next slot.",
		],
		["Result `Skipped` / `Failed`", "`reminder_state` set accordingly; a failed attempt stays retryable."],
	],
	[40, 60],
)
h3("6.3 Interval arithmetic")
p(
	"The next due slot is `max(last_remark_on, last_reminder_sent_on) + reminder_in_days`, snapped "
	"to midnight. Two properties follow:"
)
ul(
	[
		"**A remark resets the cycle.** Someone who updates a task is not chased again until the full "
		"interval has passed since that update.",
		"**The interval cannot drift.** Because the slot is a date, not a datetime, a fixed dispatch "
		"hour always finds the slot due on its own day; anchoring on a clock time would push each "
		"cycle one day later.",
	]
)
p(
	"Anchoring only on the remark would freeze the slot and suppress every repeat, which is why the "
	"last successful send participates in the maximum."
)

h2("7. WhatsApp messaging")
p("Three outbound kinds, all logged in WhatsApp Reminder Log:")
table(
	["Kind", "Trigger", "Body"],
	[
		[
			"Automatic Reminder",
			"Scheduler (`dispatch_reminder`)",
			"Greeting with the concern person's name, request to update, project title, task name, latest "
			"remark and its date (or \"No update recorded yet.\"), due date, closing line.",
		],
		[
			"Manual Reminder",
			"**Send Manual Task Reminder** (Admin Master / System Manager)",
			"The same body plus the sender's optional **Additional Message** and a link to the document it "
			"was sent from. The typed note is appended, never substituted, so the project, task and latest "
			"remark always travel with it.",
		],
		[
			"Status Summary",
			"**Send Status to Admin Master**",
			"Project title, project status, total / completed / in progress / open counts, the date, and a "
			"link to the document. No per-task breakdown by design — the recipient opens the link for detail.",
		],
	],
	[20, 26, 54],
)
p(
	"`document_url(document)` builds the absolute desk URL for the record the message is about: it "
	"accepts `[doctype, name]` (as the client sends it), returns an empty string when the record is "
	"missing or the payload malformed, and rewrites the host with `public_base_url` when configured. "
	"`send_status_to_admin_master` falls back to the Project Execution's own URL when called without "
	"a document."
)
p("A manual reminder deliberately does **not** reset the automatic reminder timer.")

h2("8. Whitelisted API surface (`project_management/api.py`)")
table(
	["Method", "Purpose", "Guard"],
	[
		[
			"`task_instance_query`",
			"Link query for task instances within one project",
			"`validate_and_sanitize_search_inputs`; non-elevated users are filtered to their own assignments; "
			"no project filter returns an empty list",
		],
		[
			"`tracker_task_query`",
			"Task options for Project Tracker — project instances when the project exists, template rows "
			"before that",
			"Same; a user with no active Employee record gets nothing",
		],
		[
			"`get_template_projects(template)`",
			"Up to 20 recent live projects of a template, for the tracker's duplicate-name hint",
			"—",
		],
		[
			"`get_project_pipeline(project)`",
			"Ordered stages with status, assignee, due date and full remark history",
			"`frappe.has_permission('Project Execution', doc=project, throw=True)`",
		],
		[
			"`get_template_preview(template)`",
			"Template rows shaped like a pipeline, with stages marked `Planned`, for a tracker before its "
			"project exists",
			"`has_permission` on the template",
		],
		[
			"`send_status_to_admin_master(project, document)`",
			"Status summary to every enabled recipient; returns the body, an aggregate delivery status and "
			"the log rows",
			"`require_reminder_permission()`; throws when no recipient is configured",
		],
		[
			"`send_manual_task_reminder(task_instance, message, document)`",
			"Manual reminder to the task's assigned concern person",
			"`require_reminder_permission()`; refuses Completed tasks unless "
			"`allow_manual_reminder_for_completed`",
		],
		[
			"`permissions.can_manage_all_tasks(user)`",
			"Role probe used by the client to decide whether to render restricted buttons",
			"Read-only; the server still re-checks every restricted action",
		],
		[
			"`Project Execution.get_pipeline` / `Project Tracker.get_pipeline`",
			"Document-bound pipeline for the form renderer",
			"Document permissions",
		],
		[
			"`Project Master Template.create_project_execution`",
			"Create a live project from a submitted template",
			"Re-checks `docstatus = 1` server-side",
		],
	],
	[30, 40, 30],
)
p("`build_reminder_message(task, note=None)` is the shared body builder (not whitelisted).")

h2("9. Hooks, migrations and installation")
table(
	["Hook", "Value"],
	[
		["`after_install` / `after_migrate`", "`project_management.install.after_install`"],
		["`app_include_css`", "`/assets/project_management/css/project_management.css`"],
		[
			"`permission_query_conditions`",
			"Project Task Instance, Project Tracker → `project_management.permissions.*`",
		],
		["`has_permission`", "Project Task Instance, Project Tracker → `project_management.permissions.*`"],
		["`scheduler_events`", "`hourly_long`: `project_management.tasks.send_due_reminders`"],
	],
	[32, 68],
)
p("`after_install` creates the `Admin Master` and `Concern Person` roles (desk access) and seeds Settings.")
p("**Migration patches (`patches.txt`)**")
table(
	["Patch", "Stage", "What it repairs"],
	[
		[
			"`restore_tracker_parent_task_fields`",
			"pre-model-sync",
			"Moves tracker task updates from the old child table to parent-level `task` / `remarks` / "
			"`status`. A tracker that carried several rows becomes several trackers, each attached to its own "
			"copy of the project rather than silently sharing one.",
		],
		[
			"`split_shared_tracker_projects`",
			"pre-model-sync",
			"Gives every tracker its own Project Execution before the unique index on `Project Tracker.project` "
			"is added. The first tracker keeps the shared project; the others get their own, built from the same "
			"template.",
		],
		[
			"`link_tracker_entries_to_remark_history`",
			"post-model-sync",
			"Claims legacy remark rows for their tracker entry and re-applies the entries, correcting task "
			"instances left without a remark row or with a stale status instead of duplicating rows.",
		],
		[
			"`backfill_remark_status_change`",
			"post-model-sync",
			"Walks each task's history in order and derives `previous_status` / `status_changed` for rows "
			"written before those columns existed.",
		],
		[
			"`backfill_tracker_template_fields`",
			"post-model-sync",
			"Derives `project_template`, `project_name` and `task` for entries that only stored `project` and "
			"`task_instance`, keeping them valid and editable.",
		],
		[
			"`migrate_wip_to_open_in_progress`",
			"post-model-sync",
			"Moves existing data from the two-state WIP / Completed model to Open / In Progress / Completed. "
			"A task with no remark becomes Open, one carrying a remark becomes In Progress, and Completed is "
			"left alone. Historical remark rows and tracker entries all recorded work, so their WIP becomes "
			"In Progress; projects stored as `Active` are re-derived from their tasks and the dropped "
			"`wip_tasks` column is replaced by `open_tasks` / `in_progress_tasks`.",
		],
	],
	[27, 15, 58],
)
p("**Installation**")
code(
	"""
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app project_management
bench --site <site> migrate
"""
)

h2("10. Data lifecycle and deletion rules")
table(
	["Action", "Consequence"],
	[
		[
			"Save a new Project Tracker",
			"Creates one Project Execution and one Project Task Instance per template row; writes the first "
			"remark; refreshes project progress.",
		],
		[
			"Change Task on an existing tracker and save",
			"Appends a remark to the newly selected task. The previously selected task keeps everything "
			"written on it.",
		],
		[
			"Re-save with the same remark and status",
			"No history row is added; progress is recomputed harmlessly.",
		],
		[
			"Set a task to Completed",
			"`completed_on` stamped, reminder schedule cleared, `reminder_state = Disabled`, project counters "
			"and `progress_percent` updated; all tasks complete promotes the project to Completed.",
		],
		[
			"Delete a Project Tracker",
			"Deletes the project it owns, all its task instances and their remark history (permanently). "
			"Nothing else references them.",
		],
		[
			"Create a project from a submitted template",
			"A live project with no owning tracker; deleting it is a System Manager action.",
		],
		["Disable a Task Master / Type of Work / template", "Blocks new configuration and new projects; existing projects and history are untouched."],
		["Amend a submitted template", "A new submitted version via `amended_from`; projects already created keep their own copies."],
	],
	[34, 66],
)
note(
	"Templates are frozen by submission and live projects hold independent copies, so editing or "
	"retiring a template never rewrites a project already under way."
)

h2("11. Configuration checklist")
ol(
	[
		"Install the app and run `bench migrate`; confirm the `Admin Master` and `Concern Person` roles exist.",
		"Assign roles to users, and make sure each Concern Person has an **Active Employee** record whose "
		"`user_id` is that user — row-level permissions and reminder recipients both depend on it.",
		"Fill the Employee `cell_number` for everyone who should receive WhatsApp messages (overridable per "
		"task and per recipient row).",
		"Configure **WhatsApp Account** in frappe_whatsapp (credentials and templates).",
		"Open **Project Management Settings**: enable reminders, set the dispatch hour, set **Public Base "
		"URL** to the site's public `https://` address, and add the Admin Master status recipients.",
		"Create Task Master and Type of Work Masters records.",
		"Create and **submit** a Project Master Template with its task rows.",
		"Verify the scheduler is running (`bench doctor`); reminders depend on `hourly_long`.",
	]
)

h2("12. Troubleshooting")
table(
	["Symptom", "Cause and fix"],
	[
		[
			"\"Project Master Template … must be submitted before it can be used\"",
			"The template is still a draft, or disabled. Submit it and clear `disabled`.",
		],
		[
			"\"Task … is not part of project …\"",
			"The selected Task Master has no instance in this project — typically a task added to the "
			"template after the project was created. Projects hold their own copies by design.",
		],
		[
			"\"You are not the assigned Concern Person for this task\"",
			"A non-elevated user is reporting on someone else's task, or the user has no active Employee "
			"record mapped by `user_id`.",
		],
		["Task list in the tracker is empty", "The user has no active Employee record, or no template row / task instance is assigned to them."],
		[
			"No reminders are sent",
			"Check in order: `enable_whatsapp_reminders`; `reminder_send_hour` vs. the server clock; the "
			"scheduler is enabled; task is Open or In Progress with `enable_reminders` and a positive "
			"interval; `next_reminder_due` is in the past; the concern person has a mobile number.",
		],
		[
			"Log row shows Skipped",
			"Read `skip_reason`: reminders disabled globally, no recipient number, the task has been "
			"Completed, or reminders disabled on the task.",
		],
		[
			"Log row shows Failed",
			"Read `error_response` and the Error Log entry \"Project Management WhatsApp send failed\". The "
			"attempt stays retryable and reuses the same log row on the next run.",
		],
		[
			"Links in messages are not tappable",
			"`public_base_url` is blank or points at `localhost`/an IP. Set a real `https://` domain.",
		],
		[
			"\"No Admin Master recipient configured\"",
			"Settings has no recipient row with `enabled = 1` and a number.",
		],
		[
			"Project status looks wrong",
			"An explicit Project Status on a tracker entry overrides the derived status; Cancelled is never "
			"revived and On Hold is not demoted by partial progress. Clear the field to return to derived "
			"status.",
		],
	],
	[34, 66],
)

h2("13. Source map")
table(
	["Path", "Contents"],
	[
		["`project_management/hooks.py`", "Permissions hooks, scheduler events, install hooks, CSS include"],
		["`project_management/api.py`", "Whitelisted endpoints, link queries, message bodies, URL rewriting"],
		["`project_management/tasks.py`", "Reminder scheduler and per-task dispatch"],
		["`project_management/whatsapp.py`", "Outbound layer, logging, idempotency, provider outcome"],
		["`project_management/permissions.py`", "Role probe, row-level conditions, action gate"],
		["`project_management/install.py`", "Role creation and Settings defaults"],
		["`project_management/patches/`", "Five migration patches"],
		["`…/project_masters/doctype/`", "Task Master, Type of Work Masters, Project Master Template, Project Task Detail"],
		[
			"`…/project_management_for_lands_constructions_etc/doctype/`",
			"Project Execution, Project Task Instance, Task Remarks History, Project Tracker, WhatsApp "
			"Reminder Log, WhatsApp Status Recipient, Project Management Settings",
		],
		["`project_management/public/css/project_management.css`", "Pipeline and remark-trail styling"],
	],
	[34, 66],
)


# ----------------------------------------------------------------- renderers --

BOLD = re.compile(r"\*\*(.+?)\*\*")
CODE = re.compile(r"`([^`]+)`")


def split_inline(text):
	"""Yield (text, bold, code). Bold spans may contain code spans and vice versa."""
	pos = 0
	for match in BOLD.finditer(text):
		if match.start() > pos:
			yield from _code_runs(text[pos : match.start()], False)
		yield from _code_runs(match.group(1), True)
		pos = match.end()
	if pos < len(text):
		yield from _code_runs(text[pos:], False)


def _code_runs(chunk, bold):
	"""Split a chunk on `code` spans, keeping the inherited bold flag."""
	for idx, part in enumerate(CODE.split(chunk)):
		if part:
			yield part, bold, bool(idx % 2)


# ---- HTML / PDF

def html_inline(text):
	out = []
	for chunk, bold, code in split_inline(text):
		esc = html.escape(chunk)
		if code:
			esc = f"<code>{esc}</code>"
		if bold:
			esc = f"<strong>{esc}</strong>"
		out.append(esc)
	return "".join(out)


def html_table(headers, rows, widths, field_mode=False):
	cols = len(headers)
	colgroup = ""
	if widths:
		colgroup = "<colgroup>" + "".join(f'<col style="width:{w}%">' for w in widths) + "</colgroup>"
	out = [f'<table>{colgroup}<thead><tr>' + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead><tbody>"]
	for row in rows:
		if field_mode and row[0] == "section":
			out.append(f'<tr class="sect"><td colspan="{cols}">{html.escape(row[1])}</td></tr>')
			continue
		cells = row[1] if field_mode else row
		out.append("<tr>" + "".join(f"<td>{html_inline(str(c))}</td>" for c in cells) + "</tr>")
	out.append("</tbody></table>")
	return "".join(out)


CSS = """
@page { size: A4; margin: 17mm 15mm 17mm 15mm; }
body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 9.3pt; color: #1b1b1b; line-height: 1.45; }
h1 { font-size: 20pt; color: #16365c; border-bottom: 2.5px solid #16365c; padding-bottom: 6px; margin: 0 0 14px; }
h2 { font-size: 13.5pt; color: #16365c; margin: 20px 0 7px; border-bottom: 1px solid #c3d0e0; padding-bottom: 3px;
     page-break-after: avoid; }
h3 { font-size: 11pt; color: #23507f; margin: 15px 0 5px; page-break-after: avoid; }
p { margin: 5px 0; text-align: justify; }
ul, ol { margin: 5px 0 5px 18px; padding: 0; }
li { margin: 2.5px 0; }
table { border-collapse: collapse; width: 100%; margin: 7px 0 11px; page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #9fb0c4; padding: 3.5px 5px; font-size: 8.4pt; vertical-align: top; text-align: left; }
th { background: #dce6f1; color: #16365c; font-weight: bold; }
tr.sect td { background: #eef3f9; font-weight: bold; color: #16365c; font-size: 8.6pt; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.1pt; background: #f2f4f7; padding: 0 2px; }
pre { font-family: "DejaVu Sans Mono", monospace; font-size: 8pt; background: #f6f8fa; border: 1px solid #ccd6e0;
      border-left: 3px solid #16365c; padding: 7px 9px; white-space: pre; page-break-inside: avoid; }
div.note { background: #fdf6e3; border-left: 3px solid #d9a700; padding: 6px 9px; margin: 8px 0; font-size: 8.9pt; }
"""


def build_html():
	parts = [
		"<!DOCTYPE html><html><head><meta charset='utf-8'>",
		"<title>Project Management — Technical and Functional Documentation</title>",
		f"<style>{CSS}</style></head><body>",
	]
	for kind, payload in B:
		if kind in ("h1", "h2", "h3"):
			parts.append(f"<{kind}>{html_inline(payload)}</{kind}>")
		elif kind == "p":
			parts.append(f"<p>{html_inline(payload)}</p>")
		elif kind == "ul":
			parts.append("<ul>" + "".join(f"<li>{html_inline(i)}</li>" for i in payload) + "</ul>")
		elif kind == "ol":
			parts.append("<ol>" + "".join(f"<li>{html_inline(i)}</li>" for i in payload) + "</ol>")
		elif kind == "table":
			headers, rows, widths = payload
			parts.append(html_table(headers, rows, widths))
		elif kind == "ftable":
			headers, rows = payload
			parts.append(html_table(headers, rows, [11, 13, 9, 17, 7, 17, 26], field_mode=True))
		elif kind == "code":
			parts.append(f"<pre>{html.escape(payload)}</pre>")
		elif kind == "note":
			parts.append(f"<div class='note'>{html_inline(payload)}</div>")
	parts.append("</body></html>")
	return "".join(parts)


# ---- DOCX

def build_docx(path):
	from docx import Document
	from docx.enum.table import WD_TABLE_ALIGNMENT
	from docx.enum.text import WD_ALIGN_PARAGRAPH
	from docx.oxml import OxmlElement
	from docx.oxml.ns import qn
	from docx.shared import Inches, Mm, Pt, RGBColor

	doc = Document()

	section = doc.sections[0]
	# A4, matching the PDF; python-docx defaults to Letter.
	section.page_width = Mm(210)
	section.page_height = Mm(297)
	section.top_margin = Inches(0.7)
	section.bottom_margin = Inches(0.7)
	section.left_margin = Inches(0.65)
	section.right_margin = Inches(0.65)
	usable = section.page_width - section.left_margin - section.right_margin

	normal = doc.styles["Normal"]
	normal.font.name = "Calibri"
	normal.font.size = Pt(9.5)
	normal.paragraph_format.space_after = Pt(4)

	NAVY = RGBColor(0x16, 0x36, 0x5C)
	for name, size, color in (("Heading 1", 19, NAVY), ("Heading 2", 13.5, NAVY), ("Heading 3", 11.5, RGBColor(0x23, 0x50, 0x7F))):
		st = doc.styles[name]
		st.font.name = "Calibri"
		st.font.size = Pt(size)
		st.font.bold = True
		st.font.color.rgb = color

	def shade(cell, hexcolor):
		tcpr = cell._tc.get_or_add_tcPr()
		shd = OxmlElement("w:shd")
		shd.set(qn("w:val"), "clear")
		shd.set(qn("w:fill"), hexcolor)
		tcpr.append(shd)

	def repeat_header(row):
		trpr = row._tr.get_or_add_trPr()
		el = OxmlElement("w:tblHeader")
		el.set(qn("w:val"), "true")
		trpr.append(el)

	def write_runs(par, text):
		for chunk, bold, code in split_inline(text):
			run = par.add_run(chunk)
			run.bold = bold
			if code:
				run.font.name = "Consolas"
				run.font.size = Pt(8.5)

	def add_table(headers, rows, widths, field_mode=False):
		cols = len(headers)
		tbl = doc.add_table(rows=1, cols=cols)
		tbl.style = "Table Grid"
		tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
		tbl.autofit = False
		if widths:
			for idx, pct in enumerate(widths):
				w = int(usable * pct / 100)
				for c in tbl.columns[idx].cells:
					c.width = w
		hdr = tbl.rows[0]
		repeat_header(hdr)
		# Word autofits by default and would ignore the column widths; a fixed layout
		# keeps the generated proportions in both Word and LibreOffice.
		layout = OxmlElement("w:tblLayout")
		layout.set(qn("w:type"), "fixed")
		tbl._tbl.tblPr.append(layout)

		for idx, head in enumerate(headers):
			cell = hdr.cells[idx]
			cell.text = ""
			par = cell.paragraphs[0]
			par.paragraph_format.space_after = Pt(1)
			run = par.add_run(head)
			run.bold = True
			run.font.size = Pt(8.5)
			run.font.color.rgb = NAVY
			shade(cell, "DCE6F1")

		for row in rows:
			tr = tbl.add_row()
			if field_mode and row[0] == "section":
				cell = tr.cells[0]
				merged = cell.merge(tr.cells[-1])
				merged.text = ""
				par = merged.paragraphs[0]
				par.paragraph_format.space_after = Pt(1)
				run = par.add_run(row[1])
				run.bold = True
				run.font.size = Pt(8.5)
				run.font.color.rgb = NAVY
				shade(merged, "EEF3F9")
				continue
			cells = row[1] if field_mode else row
			for idx, value in enumerate(cells):
				cell = tr.cells[idx]
				cell.text = ""
				par = cell.paragraphs[0]
				par.paragraph_format.space_after = Pt(1)
				write_runs(par, str(value))
				for run in par.runs:
					if run.font.size is None:
						run.font.size = Pt(8.5)
			if widths:
				for idx, pct in enumerate(widths):
					tr.cells[idx].width = int(usable * pct / 100)
		doc.add_paragraph().paragraph_format.space_after = Pt(2)

	for kind, payload in B:
		if kind == "h1":
			par = doc.add_heading(level=1)
			write_runs(par, payload)
		elif kind == "h2":
			par = doc.add_heading(level=2)
			write_runs(par, payload)
		elif kind == "h3":
			par = doc.add_heading(level=3)
			write_runs(par, payload)
		elif kind == "p":
			par = doc.add_paragraph()
			par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
			write_runs(par, payload)
		elif kind in ("ul", "ol"):
			style = "List Bullet" if kind == "ul" else "List Number"
			for item in payload:
				par = doc.add_paragraph(style=style)
				write_runs(par, item)
		elif kind == "table":
			headers, rows, widths = payload
			add_table(headers, rows, widths)
		elif kind == "ftable":
			headers, rows = payload
			# Fieldnames are long snake_case tokens: give that column room so Word
			# does not break them mid-identifier.
			add_table(headers, rows, [19, 12, 7, 15, 6, 15, 26], field_mode=True)
		elif kind == "code":
			par = doc.add_paragraph()
			par.paragraph_format.left_indent = Inches(0.15)
			run = par.add_run(payload)
			run.font.name = "Consolas"
			run.font.size = Pt(8.5)
		elif kind == "note":
			par = doc.add_paragraph()
			par.paragraph_format.left_indent = Inches(0.15)
			run = par.add_run("Note: ")
			run.bold = True
			write_runs(par, payload)
			for cell_run in par.runs:
				if cell_run.font.size is None:
					cell_run.font.size = Pt(9)

	doc.save(path)


def main():
	os.makedirs(OUT, exist_ok=True)
	pdf_path = os.path.join(OUT, "Project_Management_Technical_Functional_Documentation.pdf")
	docx_path = os.path.join(OUT, "Project_Management_Technical_Functional_Documentation.docx")

	with tempfile.TemporaryDirectory() as tmp:
		html_path = os.path.join(tmp, "doc.html")
		with open(html_path, "w") as fh:
			fh.write(build_html())

		subprocess.run(
			[
				"wkhtmltopdf", "--quiet", "--enable-local-file-access",
				"--margin-top", "17mm", "--margin-bottom", "17mm",
				"--footer-font-size", "7", "--footer-right", "Page [page] of [topage]",
				"--footer-left", "Project Management — Technical and Functional Documentation",
				html_path, pdf_path,
			],
			check=True,
		)

	build_docx(docx_path)
	for pth in (pdf_path, docx_path):
		print(pth, os.path.getsize(pth), "bytes")


if __name__ == "__main__":
	main()
