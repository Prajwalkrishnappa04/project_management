### Project Management for lands constructions etc

Configurable project management for a business owner running many types of business.
Administrators configure reusable masters and project templates; employees only pick a
project and task, type remarks, choose a status, and save.

### Data model

| DocType | Module | Role |
|---|---|---|
| Task Master | Project Masters | Reusable task names (`TASK-####`). |
| Type of Work Masters | Project Masters | Work categories such as Land / Construction / Trading (`WORK-####`). |
| Project Master Template | Project Masters | Submittable template: work type + task rows. |
| Project Task Detail | Project Masters | Template child row: task, concern person, completion timeline, reminder interval. |
| Project Execution | Project Management for lands… | Live project created from a submitted template (`PM-PRJ-#####`). |
| Project Task Instance | Project Management for lands… | Per-project task with its own status, due date and reminder state (`PM-TASK-#####`). |
| Task Remarks History | Project Management for lands… | Append-only remark history on a task instance. |
| Project Tracker | Project Management for lands… | Employee entry screen; owns one live project (`PM-TRK-####`). |
| WhatsApp Reminder Log | Project Management for lands… | Every outbound attempt: payload, provider id, status, error (`PM-WA-#####`). |
| Project Management Settings | Project Management for lands… | Reminder switches and Admin Master status recipients. |

A template is reusable: two live projects created from the same template track their own
status, assignees, due dates, remarks and reminders independently.

### Flow

1. Create **Task Master** and **Type of Work Masters** records.
2. Create a **Project Master Template**, add task rows (task, concern person, completion
   timeline in days, reminder in days), then **Submit**.
3. In **Project Tracker**, the employee picks the **Project Template**, types a **Project
   Name** and optionally a start date. The template's task rows are previewed as a pipeline
   before the save.
4. In the **Entry Form**, pick the task and write the remarks. The status defaults to
   **Open**; saving a remark moves the task to **In Progress** on its own, and only an
   explicit choice of **Completed** closes it.
5. On save the tracker creates **its own Project Execution** plus one **Project Task
   Instance** per template row, with `due_date = start date + completion timeline` and the
   first reminder scheduled, then writes the remark to the selected task. Template, project
   name and start date become read-only (`set_only_once`): the live project and its due
   dates are derived from them.
6. Every save **appends** to the selected task's **Task Remarks History** and never
   overwrites an earlier remark: the pipeline shows the full trail, newest first. To
   report the next task of the same project, change **Task** on the same tracker entry,
   write the new remark and save — the previous task keeps everything written on it.
   Re-saving without changing the remark or status adds nothing.
7. Completing a task sets `completed_on`, clears the reminder schedule and updates the
   project's progress counters.

#### Task status

A task instance moves through three states, and only one of them is ever set by hand:

| Status | Set by |
| --- | --- |
| **Open** | the default; every task instance is created Open, because nothing has been reported on it yet |
| **In Progress** | automatic — writing a remark on an Open task promotes it, since the remark *is* the record that work started |
| **Completed** | manual only; the person writing the remark chooses it, and no progress calculation ever sets or clears it |

The same three states roll up to the project: `Open` while no task has been touched,
`In Progress` once any task is under way, `Completed` when every task is. A manual
**On Hold** or **Cancelled** on the project is never overridden by progress.

One tracker owns exactly one project (`Project Tracker.project` is unique): a new tracker
always creates a new project, even when the project name repeats. Deleting a tracker deletes
its project, task instances and remark history, because nothing else references them.

**Project Execution** remains a first-class doctype: open it to view progress, or create one
directly from a submitted template via **Create Live Project** (that project then has no
owning tracker).

### Reminders

`project_management.tasks.send_due_reminders` runs hourly (`hourly_long`) and only acts in
the hour set as **Reminder Send Hour** (`0` is a valid hour), then enqueues one background
job per due task. Before sending, `dispatch_reminder` reloads the task and:

- skips and logs if the task has been Completed;
- restarts the timer instead of sending if a newer remark exists;
- reads the interval from the task instance (copied from Project Master) — never hardcoded;
- recomputes the due slot as `max(last remark, last successful send) + Reminder in Days`,
  snapped to midnight so a fixed dispatch hour cannot make the interval drift.

Each send uses an idempotency key of task + due date, so a retried job never sends twice on
the same day. A failed attempt stays retryable and reuses its log row.

### WhatsApp messages

Three outbound kinds, all logged in **WhatsApp Reminder Log**:

| Kind | Trigger | Body |
|---|---|---|
| Automatic Reminder | scheduler | greeting, project, task, latest remark, due date |
| Manual Reminder | **Send Manual Task Reminder** | same, plus the sender's optional **Additional Message** and a link to the document it was sent from. The typed note is appended, never substituted, so the project, task and latest remarks always travel with it |
| Status Summary | **Send Status to Admin Master** | project, status, task counts, date and a link to the document — no per-task breakdown; the recipient opens the link for detail |

Both buttons pass the record currently open, so the link points at that Project Tracker;
`send_status_to_admin_master` falls back to the Project Execution when called without one.

WhatsApp only renders a URL as a tappable link when its host looks like a real domain, so
`http://127.0.0.1:8007/...` or a `localhost` address arrives as plain text. Set **Public
Base URL** in Project Management Settings to the site's public `https://` address; it
replaces the host in every outgoing link. Left blank, the site's own URL is used.


### Roles

`Admin Master` and `System Manager` see all tasks and may use **Send Status to Admin Master**
and **Send Manual Task Reminder**. A `Concern Person` sees and updates only their assigned
tasks, and may create a tracker entry (which creates its live project). These rules are
enforced on the server via `permission_query_conditions`, `has_permission` and explicit
checks — button visibility is never treated as authorization.

### Configuration

Set WhatsApp credentials in **WhatsApp Account** (frappe_whatsapp), then open
**Project Management Settings** to enable reminders, set the dispatch hour, add the Admin
Master status recipients, and set the **Public Base URL** used for links in messages.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app project_management
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/project_management
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
