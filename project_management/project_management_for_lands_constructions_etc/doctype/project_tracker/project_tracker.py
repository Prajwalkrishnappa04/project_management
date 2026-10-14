# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, nowdate

from project_management.project_management_for_lands_constructions_etc.doctype.project_task_instance.project_task_instance import (
	get_employee_for_user,
)


class ProjectTracker(Document):
	"""One tracker owns one Project Execution.

	The employee picks a template, names the project, picks a task and writes the
	remark. Saving creates that live project and its task instances.
	"""

	def before_insert(self):
		self.project = self.create_project()

	def validate(self):
		if not self.project:
			frappe.throw(_("Live Project is not set on this entry"))

		self.task_instance = self.resolve_task_instance()
		self.validate_assignment()

		self.entry_datetime = self.entry_datetime or now_datetime()
		self.entered_by = self.entered_by or frappe.session.user
		if not self.concern_person:
			self.concern_person = get_employee_for_user(frappe.session.user) or frappe.db.get_value(
				"Project Task Instance", self.task_instance, "concern_person"
			)

		self.remarks = (self.remarks or "").strip()
		if not self.remarks:
			frappe.throw(_("Remarks are required"))

	def create_project(self):
		"""Create this tracker's own live project from the template."""
		template = self.project_template
		title = (self.project_name or "").strip()
		if not template:
			frappe.throw(_("Project Template is required"))
		if not title:
			frappe.throw(_("Project Name is required"))
		self.project_name = title

		docstatus, disabled = frappe.db.get_value(
			"Project Master Template", template, ["docstatus", "disabled"]
		)
		if docstatus != 1:
			frappe.throw(
				_("Project Master Template {0} must be submitted before it can be used").format(
					frappe.bold(template)
				)
			)
		if disabled:
			frappe.throw(_("Project Master Template {0} is disabled").format(frappe.bold(template)))

		# Creating the project is an Admin Master / System Manager action in Project
		# Execution's own permissions; a Concern Person recording the first update of
		# a project must not be blocked by that. The payload is fully constrained.
		execution = frappe.new_doc("Project Execution")
		execution.project_master = template
		execution.project_title = title
		execution.start_date = self.start_date or nowdate()
		execution.insert(ignore_permissions=True)
		return execution.name

	def resolve_task_instance(self):
		"""Map the chosen Task Master row to this project's own task instance."""
		if not self.task:
			frappe.throw(_("Task is required"))

		instance = frappe.db.get_value(
			"Project Task Instance",
			{"project_execution": self.project, "task": self.task},
			"name",
		)
		if not instance:
			frappe.throw(
				_("Task {0} is not part of project {1}").format(
					frappe.bold(self.task), frappe.bold(self.project_name or self.project)
				)
			)
		return instance

	def validate_assignment(self):
		"""Spec 10: a Concern Person may only update tasks assigned to them.
		Server-side enforcement; UI filtering alone is not authorization."""
		from project_management.permissions import can_manage_all_tasks

		if can_manage_all_tasks():
			return

		assigned = frappe.db.get_value("Project Task Instance", self.task_instance, "concern_person")
		employee = get_employee_for_user(frappe.session.user)
		if not employee or assigned != employee:
			frappe.throw(
				_("You are not the assigned Concern Person for this task"), frappe.PermissionError
			)

	def on_update(self):
		"""Spec 5/6: every save appends the remark to the selected task's history.
		Runs on insert and on every edit, so switching the task records progress on
		the new one while the earlier task keeps everything written on it."""
		self.apply_to_task_instance()

	def on_trash(self):
		"""Delete the project this tracker owns, with its tasks and remark history.

		The tracker is the only thing that referenced this project, so leaving it
		behind would strand a project nothing can reach or update."""
		if not self.project or not frappe.db.exists("Project Execution", self.project):
			return

		for instance in frappe.get_all(
			"Project Task Instance", filters={"project_execution": self.project}, pluck="name"
		):
			frappe.delete_doc(
				"Project Task Instance", instance, force=True, ignore_permissions=True, delete_permanently=True
			)

		frappe.delete_doc(
			"Project Execution", self.project, force=True, ignore_permissions=True, delete_permanently=True
		)

	def apply_to_task_instance(self):
		"""Spec 5/6: append this entry's remark to the task and refresh progress."""
		instance = frappe.get_doc("Project Task Instance", self.task_instance)
		instance.sync_tracker_remark(
			self.name,
			self.remarks,
			self.status,
			concern_person=self.concern_person,
			entry_datetime=self.entry_datetime,
			entered_by=self.entered_by,
		)
		# An explicit Project Status on the entry overrides the progress-derived status.
		frappe.get_doc("Project Execution", self.project).update_progress(status=self.project_status)

	@frappe.whitelist()
	def get_pipeline(self):
		from project_management.api import get_project_pipeline

		return get_project_pipeline(self.project)
