# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, nowdate


class ProjectExecution(Document):
	def validate(self):
		if not self.start_date:
			self.start_date = nowdate()

	def after_insert(self):
		self.create_task_instances()
		self.update_progress()

	def create_task_instances(self):
		"""Spec 7: a live project owns independent task instances copied from the template."""
		template = frappe.get_doc("Project Master Template", self.project_master)
		if template.docstatus != 1:
			frappe.throw(_("Project Master Template {0} must be submitted").format(self.project_master))

		for row in template.task_details:
			instance = frappe.new_doc("Project Task Instance")
			instance.project_execution = self.name
			instance.task = row.task
			instance.task_name = row.task_name or frappe.db.get_value("Task Master", row.task, "task_master")
			instance.sequence = row.idx
			instance.concern_person = row.concern_person
			instance.current_status = "WIP"
			instance.activation_date = self.start_date
			instance.completion_timeline_in_days = row.completion_timeline_in_days
			instance.enable_reminders = row.enable_reminders
			instance.reminder_in_days = row.reminder_in_days
			instance.insert(ignore_permissions=True)

	def update_progress(self, status=None):
		rows = frappe.get_all(
			"Project Task Instance",
			filters={"project_execution": self.name},
			fields=["current_status", "due_date"],
		)

		total = len(rows)
		completed = len([r for r in rows if r.current_status == "Completed"])
		wip = total - completed
		due_dates = [r.due_date for r in rows if r.due_date]

		self.db_set(
			{
				"total_tasks": total,
				"completed_tasks": completed,
				"wip_tasks": wip,
				"progress_percent": flt(completed * 100.0 / total, 2) if total else 0,
				"expected_end_date": max(due_dates) if due_dates else None,
				"status": self.derive_status(total, completed, status),
			},
			update_modified=False,
		)

	def derive_status(self, total, completed, status=None):
		"""An explicit choice always wins. Otherwise every task being done promotes the
		project to Completed; a Cancelled project is never revived by progress."""
		if status:
			return status

		if self.status == "Cancelled":
			return self.status

		if total and completed == total:
			return "Completed"

		# Partial progress must not demote a manual On Hold back to Active.
		if self.status == "On Hold":
			return self.status

		return "Active"

	@frappe.whitelist()
	def get_pipeline(self):
		from project_management.api import get_project_pipeline

		return get_project_pipeline(self.name)
