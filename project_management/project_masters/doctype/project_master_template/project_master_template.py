# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ProjectMasterTemplate(Document):
	def validate(self):
		self.validate_tasks()

	def validate_tasks(self):
		"""Spec 12: Project Master cannot be submitted without required fields and valid task rows."""
		if not self.task_details:
			frappe.throw(_("At least one task row is required in Task Details"))

		seen = set()
		for row in self.task_details:
			if row.task in seen:
				frappe.throw(
					_("Row {0}: Task {1} is duplicated. Each task may appear only once in a template.").format(
						row.idx, frappe.bold(row.task)
					)
				)
			seen.add(row.task)

			if (row.completion_timeline_in_days or 0) <= 0:
				frappe.throw(
					_("Row {0}: Completion Timeline in Days must be a positive integer").format(row.idx)
				)

			if row.enable_reminders and (row.reminder_in_days or 0) <= 0:
				frappe.throw(
					_("Row {0}: Reminder in Days must be a positive integer when reminders are enabled").format(
						row.idx
					)
				)

			if not row.enable_reminders:
				row.reminder_in_days = 0

	@frappe.whitelist()
	def create_project_execution(self, project_title=None, start_date=None):
		"""Spec 13: create a live Project Execution from a submitted Project Master."""
		if self.docstatus != 1:
			frappe.throw(_("Submit the Project Master Template before creating a live project"))

		execution = frappe.new_doc("Project Execution")
		execution.project_master = self.name
		execution.project_title = project_title or self.project_name
		execution.type_of_work = self.type_of_work
		execution.start_date = start_date or frappe.utils.nowdate()
		execution.insert()
		return execution.name
