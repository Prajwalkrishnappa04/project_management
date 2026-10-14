# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Move Project Tracker task updates back to parent-level fields.

The task-update child table is replaced by task / remarks / status on the tracker
itself. A tracker that carried several rows becomes several trackers — but a tracker
owns its project, so the extra trackers are attached to their own copy of the project
rather than silently sharing one.
"""

import frappe


def execute():
	if not frappe.db.table_exists("Project Tracker Task Update"):
		return

	# The tracker no longer declares this table, but its DocType record would still
	# make every tracker load try to import the deleted child controller.
	frappe.reload_doc("project_management_for_lands_constructions_etc", "doctype", "project_tracker")
	frappe.db.delete("DocField", {"options": "Project Tracker Task Update"})
	frappe.db.delete("DocType", {"name": "Project Tracker Task Update"})
	frappe.clear_cache(doctype="Project Tracker")

	rows = frappe.db.sql(
		"""
		SELECT parent, name, idx, task, task_name, remarks, status, entry_datetime, task_instance
		FROM `tabProject Tracker Task Update`
		ORDER BY parent, idx
		""",
		as_dict=True,
	)
	if not rows:
		return

	by_parent = {}
	for row in rows:
		by_parent.setdefault(row.parent, []).append(row)

	for parent, parent_rows in by_parent.items():
		if not frappe.db.exists("Project Tracker", parent):
			continue

		first = parent_rows[0]
		frappe.db.set_value(
			"Project Tracker",
			parent,
			{
				"task": first.task,
				"task_name": first.task_name,
				"remarks": first.remarks,
				"status": first.status or "WIP",
				"task_instance": first.task_instance,
			},
			update_modified=False,
		)

		for extra in parent_rows[1:]:
			split_into_own_tracker(parent, extra)

	frappe.db.commit()
	frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabProject Tracker Task Update`")


def split_into_own_tracker(parent, row):
	"""Give a surplus task-update row its own tracker and its own project copy."""
	source = frappe.db.get_value(
		"Project Tracker",
		parent,
		["project_template", "project_name", "start_date", "entered_by", "concern_person"],
		as_dict=True,
	)

	tracker = frappe.new_doc("Project Tracker")
	tracker.project_template = source.project_template
	tracker.project_name = f"{source.project_name} ({row.task_name or row.task})"
	tracker.start_date = source.start_date
	tracker.task = row.task
	tracker.remarks = row.remarks
	tracker.status = row.status or "WIP"
	tracker.entry_datetime = row.entry_datetime
	tracker.entered_by = source.entered_by
	tracker.concern_person = source.concern_person
	tracker.insert(ignore_permissions=True)

	# The remark this row wrote belongs to the old project's task instance, which is
	# no longer this tracker's; drop it so the old project does not keep a status
	# that nothing claims.
	if row.task_instance and frappe.db.exists("Project Task Instance", row.task_instance):
		frappe.get_doc("Project Task Instance", row.task_instance).remove_tracker_remark(parent)
