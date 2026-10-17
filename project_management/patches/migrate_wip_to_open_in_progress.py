# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Move existing data from the two-state WIP / Completed model to Open / In Progress / Completed.

The old model had no way to say "nothing has happened yet": a task was WIP from the
moment the project was created until somebody closed it. The new model splits that:

- a task that was never remarked on becomes **Open**;
- a task that carries at least one remark becomes **In Progress**, because the remark
  is the record of work having started;
- **Completed** is untouched — it was a deliberate choice then and stays one now.

Every historical remark row says WIP for the same reason, so those become In Progress.
Project Execution's old `Active` and the dropped `wip_tasks` counter are rebuilt from
the task instances by `update_progress`.
"""

import frappe

from project_management.status import IN_PROGRESS, OPEN


def execute():
	migrate_remark_history()
	migrate_task_instances()
	migrate_trackers()
	migrate_projects()
	frappe.db.commit()


def migrate_remark_history():
	"""Every remark row recorded work, so a WIP stamp on one means In Progress."""
	if not frappe.db.table_exists("Task Remarks History"):
		return

	for column in ("status_at_entry", "previous_status"):
		if frappe.db.has_column("Task Remarks History", column):
			frappe.db.sql(
				f"UPDATE `tabTask Remarks History` SET `{column}` = %s WHERE `{column}` = 'WIP'",
				IN_PROGRESS,
			)


def migrate_task_instances():
	"""A remarked task has started (In Progress); an untouched one is still Open."""
	if not frappe.db.table_exists("Project Task Instance"):
		return

	remarked = set(
		frappe.get_all(
			"Task Remarks History",
			filters={"parenttype": "Project Task Instance"},
			pluck="parent",
		)
	)

	for name in frappe.get_all(
		"Project Task Instance", filters={"current_status": "WIP"}, pluck="name"
	):
		frappe.db.set_value(
			"Project Task Instance",
			name,
			"current_status",
			IN_PROGRESS if name in remarked else OPEN,
			update_modified=False,
		)


def migrate_trackers():
	"""A tracker entry always carries a remark, so its WIP meant In Progress."""
	if not frappe.db.table_exists("Project Tracker"):
		return

	frappe.db.sql(
		"UPDATE `tabProject Tracker` SET `status` = %s WHERE `status` = 'WIP'", IN_PROGRESS
	)
	frappe.db.sql(
		"UPDATE `tabProject Tracker` SET `project_status` = %s WHERE `project_status` = 'Active'",
		IN_PROGRESS,
	)


def migrate_projects():
	"""Rebuild each project's status and the new counters from its own tasks.

	`Active` had no equivalent: a project with no work done yet is Open and one with
	work under way is In Progress, which only the task rows can tell apart. On Hold
	and Cancelled were manual choices and are left alone.
	"""
	if not frappe.db.table_exists("Project Execution"):
		return

	for name in frappe.get_all("Project Execution", pluck="name"):
		project = frappe.get_doc("Project Execution", name)

		# update_progress derives the status, but only if the stored one is not a
		# manual override it must preserve. "Active" is neither manual nor valid now.
		if project.status == "Active":
			project.db_set("status", OPEN, update_modified=False)

		project.update_progress()

	if frappe.db.has_column("Project Execution", "wip_tasks"):
		frappe.db.sql_ddl("ALTER TABLE `tabProject Execution` DROP COLUMN `wip_tasks`")
