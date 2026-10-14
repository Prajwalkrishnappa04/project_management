# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Backfill Project Tracker.project_template, project_name and task.

Entries created before the tracker became the project entry screen only stored
`project` and `task_instance`. Derive the new fields from them so existing
entries stay valid and editable (project_name and task are mandatory).
"""

import frappe


def execute():
	trackers = frappe.get_all(
		"Project Tracker",
		filters={"project": ["is", "set"]},
		fields=["name", "project", "task_instance"],
	)

	for tracker in trackers:
		execution = frappe.db.get_value(
			"Project Execution", tracker.project, ["project_master", "project_title"], as_dict=True
		)
		if not execution:
			continue

		values = {
			"project_template": execution.project_master,
			"project_name": execution.project_title,
			"start_date": frappe.db.get_value("Project Execution", tracker.project, "start_date"),
		}

		if tracker.task_instance:
			values["task"] = frappe.db.get_value("Project Task Instance", tracker.task_instance, "task")

		frappe.db.set_value("Project Tracker", tracker.name, values, update_modified=False)

	frappe.db.commit()
