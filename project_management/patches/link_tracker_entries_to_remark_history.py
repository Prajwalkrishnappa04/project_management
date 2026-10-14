# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Backfill Task Remarks History.tracker_entry and re-apply tracker entries.

Entries saved before Project Tracker synced on update left the task instance
without a remark row and with a stale status. Claim the matching legacy rows
first so the re-sync corrects them instead of duplicating them.
"""

import frappe


def execute():
	trackers = frappe.get_all(
		"Project Tracker",
		fields=["name", "task_instance", "project", "remarks", "entry_datetime"],
		order_by="creation asc",
	)

	for tracker in trackers:
		if not tracker.task_instance or not frappe.db.exists(
			"Project Task Instance", tracker.task_instance
		):
			continue

		claim_legacy_row(tracker)

		doc = frappe.get_doc("Project Tracker", tracker.name)
		doc.apply_to_task_instance()

	frappe.db.commit()


def claim_legacy_row(tracker):
	"""Attach an unowned history row written by the old append_remark() path."""
	match = frappe.db.get_value(
		"Task Remarks History",
		{
			"parent": tracker.task_instance,
			"parenttype": "Project Task Instance",
			"tracker_entry": ("in", (None, "")),
			"remarks": (tracker.remarks or "").strip(),
		},
		"name",
		order_by="entry_datetime asc",
	)
	if match:
		frappe.db.set_value("Task Remarks History", match, "tracker_entry", tracker.name)
