# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Backfill previous_status / status_changed on existing remark history rows.

Rows written before the audit columns existed have no record of the status they
replaced. Walk each task's history in order and derive it from the preceding row.
"""

import frappe


def execute():
	parents = set(
		frappe.get_all(
			"Task Remarks History",
			filters={"parenttype": "Project Task Instance"},
			pluck="parent",
		)
	)

	for parent in parents:
		history = frappe.get_all(
			"Task Remarks History",
			filters={"parent": parent, "parenttype": "Project Task Instance"},
			fields=["name", "status_at_entry"],
			order_by="entry_datetime asc, idx asc",
		)

		previous_status = None
		for entry in history:
			frappe.db.set_value(
				"Task Remarks History",
				entry.name,
				{
					"previous_status": previous_status,
					"status_changed": 1
					if previous_status and previous_status != entry.status_at_entry
					else 0,
				},
				update_modified=False,
			)
			previous_status = entry.status_at_entry

	frappe.db.commit()
