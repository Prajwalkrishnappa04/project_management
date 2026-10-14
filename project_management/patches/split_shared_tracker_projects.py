# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Give every Project Tracker its own Project Execution.

Trackers used to be able to share one live project, so a remark entered on a new
tracker landed on an earlier tracker's project. Each tracker now owns its project
(`Project Tracker.project` is unique), which this patch establishes before the
model sync tries to add that unique index.

A tracker that shared a project keeps pointing at it only if it was the first to
use it; the others get their own project built from the same template.
"""

import frappe


def execute():
	if not frappe.db.has_column("Project Tracker", "project"):
		return

	trackers = frappe.db.sql(
		"""
		SELECT name, project, project_template, project_name, start_date, task, task_instance
		FROM `tabProject Tracker`
		WHERE project IS NOT NULL AND project != ''
		ORDER BY creation ASC
		""",
		as_dict=True,
	)

	seen = set()
	for tracker in trackers:
		if tracker.project not in seen:
			seen.add(tracker.project)
			continue

		clone = clone_project(tracker)
		if not clone:
			continue

		seen.add(clone)
		repoint(tracker, clone)

	frappe.db.commit()


def clone_project(tracker):
	"""Build a fresh project from the same template for a tracker that shared one."""
	template = tracker.project_template or frappe.db.get_value(
		"Project Execution", tracker.project, "project_master"
	)
	if not template or frappe.db.get_value("Project Master Template", template, "docstatus") != 1:
		return None

	title = tracker.project_name or frappe.db.get_value(
		"Project Execution", tracker.project, "project_title"
	)

	execution = frappe.new_doc("Project Execution")
	execution.project_master = template
	execution.project_title = f"{title} ({tracker.name})"
	execution.start_date = tracker.start_date or frappe.db.get_value(
		"Project Execution", tracker.project, "start_date"
	)
	execution.insert(ignore_permissions=True)
	return execution.name


def repoint(tracker, project):
	"""Move the tracker and its remark onto the cloned project."""
	instance = None
	if tracker.task:
		instance = frappe.db.get_value(
			"Project Task Instance", {"project_execution": project, "task": tracker.task}, "name"
		)

	frappe.db.set_value(
		"Project Tracker",
		tracker.name,
		{"project": project, "task_instance": instance},
		update_modified=False,
	)

	# The remark it wrote belongs to the shared project's task; withdraw it there so
	# that project does not keep a status this tracker no longer claims.
	if tracker.task_instance and frappe.db.exists("Project Task Instance", tracker.task_instance):
		frappe.get_doc("Project Task Instance", tracker.task_instance).remove_tracker_remark(
			tracker.name
		)
