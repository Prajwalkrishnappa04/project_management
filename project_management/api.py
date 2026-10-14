# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Whitelisted endpoints for the Project Tracker screen (spec sections 4, 5, 9, 10)."""

import frappe
from frappe import _
from frappe.utils import get_url_to_form, now_datetime

from project_management.permissions import can_manage_all_tasks, require_reminder_permission
from project_management.project_management_for_lands_constructions_etc.doctype.project_task_instance.project_task_instance import (
	get_employee_for_user,
)
from project_management.whatsapp import send_whatsapp_message


def document_url(document):
	"""Absolute desk URL for the document a WhatsApp message is about.

	`document` is `[doctype, name]` (as the client sends it) or a tuple. Returns an
	empty string when it is missing or malformed, so the caller can fall back.
	"""
	if isinstance(document, str):
		document = frappe.parse_json(document)

	if not document or len(document) != 2 or not all(document):
		return ""

	doctype, name = document
	if not frappe.db.exists(doctype, name):
		return ""

	return get_url_to_form(doctype, name)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def task_instance_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for the Task field: restricted to the selected project, and for a
	Concern Person, to their own assignments (spec 4.1, 12)."""
	project = (filters or {}).get("project_execution")
	if not project:
		return []

	conditions = {"project_execution": project}
	if not can_manage_all_tasks():
		employee = get_employee_for_user(frappe.session.user)
		if not employee:
			return []
		conditions["concern_person"] = employee

	rows = frappe.get_all(
		"Project Task Instance",
		filters=conditions,
		or_filters=[["task_name", "like", f"%{txt}%"], ["name", "like", f"%{txt}%"]] if txt else None,
		fields=["name", "task_name", "current_status"],
		order_by="sequence asc",
		start=start,
		page_length=page_len,
	)
	return [(r.name, r.task_name, r.current_status) for r in rows]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def tracker_task_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for Project Tracker's Task field.

	Before the live project exists the options come from the template's task rows;
	afterwards from the project's own task instances, so a task that was removed
	from the template later is still selectable on a running project. A Concern
	Person only ever sees their own assignments (spec 4.1, 10, 12)."""
	filters = filters or {}
	project = filters.get("project_execution")
	template = filters.get("project_template")

	employee = None
	if not can_manage_all_tasks():
		employee = get_employee_for_user(frappe.session.user)
		if not employee:
			return []

	if project:
		conditions = {"project_execution": project}
		if employee:
			conditions["concern_person"] = employee
		rows = frappe.get_all(
			"Project Task Instance",
			filters=conditions,
			or_filters=[["task_name", "like", f"%{txt}%"], ["task", "like", f"%{txt}%"]] if txt else None,
			fields=["task", "task_name", "current_status"],
			order_by="sequence asc",
			start=start,
			page_length=page_len,
		)
		return [(r.task, r.task_name, r.current_status) for r in rows]

	if not template:
		return []

	conditions = {"parent": template, "parenttype": "Project Master Template"}
	if employee:
		conditions["concern_person"] = employee
	rows = frappe.get_all(
		"Project Task Detail",
		filters=conditions,
		or_filters=[["task_name", "like", f"%{txt}%"], ["task", "like", f"%{txt}%"]] if txt else None,
		fields=["task", "task_name", "employee_name"],
		order_by="idx asc",
		start=start,
		page_length=page_len,
	)
	return [(r.task, r.task_name, r.employee_name) for r in rows]


@frappe.whitelist()
def get_template_projects(template):
	"""Live projects already created from a template, for the tracker's reuse hint.

	Typing a project name that already exists continues that project; this is what
	the client shows so the user does not have to remember exact titles.
	"""
	if not template:
		return []

	return frappe.get_all(
		"Project Execution",
		filters={"project_master": template},
		fields=["name", "project_title", "status", "total_tasks", "completed_tasks"],
		order_by="modified desc",
		limit=20,
	)


@frappe.whitelist()
def get_project_pipeline(project):
	"""Spec 4.2: ordered stages with status and full remark history."""
	frappe.has_permission("Project Execution", doc=project, throw=True)

	execution = frappe.db.get_value(
		"Project Execution",
		project,
		["project_title", "status", "total_tasks", "completed_tasks"],
		as_dict=True,
	)
	if not execution:
		frappe.throw(_("Project {0} not found").format(project))

	tasks = frappe.get_all(
		"Project Task Instance",
		filters={"project_execution": project},
		fields=[
			"name",
			"sequence",
			"task",
			"task_name",
			"current_status",
			"concern_person",
			"concern_person_name",
			"due_date",
		],
		order_by="sequence asc, creation asc",
	)

	for task in tasks:
		task["remarks"] = frappe.get_all(
			"Task Remarks History",
			filters={"parent": task["name"], "parenttype": "Project Task Instance"},
			fields=[
				"remarks",
				"entry_datetime",
				"concern_person_name",
				"entered_by",
				"status_at_entry",
				"previous_status",
				"status_changed",
			],
			order_by="entry_datetime asc, idx asc",
		)

	return {
		"project": project,
		"project_title": execution.project_title,
		"project_status": execution.status,
		"total": execution.total_tasks or len(tasks),
		"completed": execution.completed_tasks or 0,
		"tasks": tasks,
	}


@frappe.whitelist()
def get_template_preview(template):
	"""The template's task rows shaped like a pipeline, for the tracker before the
	live project exists. No status or remarks exist yet, so stages render as planned."""
	if not template:
		return None

	frappe.has_permission("Project Master Template", doc=template, throw=True)

	doc = frappe.get_cached_doc("Project Master Template", template)
	tasks = [
		{
			"name": None,
			"sequence": row.idx,
			"task": row.task,
			"task_name": row.task_name,
			"current_status": "Planned",
			"concern_person": row.concern_person,
			"concern_person_name": row.employee_name,
			"due_date": None,
			"remarks": [],
		}
		for row in doc.task_details
	]

	return {
		"project": None,
		"project_title": doc.project_name,
		"project_status": "Not Created",
		"total": len(tasks),
		"completed": 0,
		"tasks": tasks,
	}


@frappe.whitelist()
def send_status_to_admin_master(project, document=None):
	"""Spec 6.2: current project status overview sent to the Admin Master recipients.

	The per-task breakdown is deliberately omitted: the message carries the counts and
	a link to the document, and the recipient reads the detail there."""
	require_reminder_permission()

	pipeline = get_project_pipeline(project)
	wip = pipeline["total"] - pipeline["completed"]

	lines = [
		"PROJECT STATUS OVERVIEW",
		f"Project: {pipeline['project_title']}",
		f"Project Status: {pipeline['project_status']}",
		f"Total tasks: {pipeline['total']} | Completed: {pipeline['completed']} | WIP: {wip}",
		f"Latest update: {frappe.utils.format_datetime(now_datetime(), 'd MMMM yyyy')}",
		f"View: {document_url(document) or document_url(('Project Execution', project))}",
	]
	summary = "\n".join(lines)

	settings = frappe.get_cached_doc("Project Management Settings")
	recipients = settings.get_status_recipients()
	if not recipients:
		frappe.throw(
			_("No Admin Master recipient configured. Add one in Project Management Settings.")
		)

	results = []
	for recipient in recipients:
		results.append(
			send_whatsapp_message(
				message=summary,
				recipient_number=recipient.get("number"),
				recipient_name=recipient.get("name"),
				recipient_employee=recipient.get("employee"),
				reminder_type="Status Summary",
				project_execution=project,
				idempotency_key=f"status::{project}::{recipient.get('number')}::{frappe.utils.now()}",
			)
		)

	delivery_status = "Sent" if any(r["delivery_status"] == "Sent" for r in results) else "Failed"
	return {"summary": summary.replace("\n", "<br>"), "delivery_status": delivery_status, "logs": results}


@frappe.whitelist()
def send_manual_task_reminder(task_instance, message=None, document=None):
	"""Spec Screen 5: manual reminder to the task's assigned concern person."""
	require_reminder_permission()

	task = frappe.get_doc("Project Task Instance", task_instance)
	settings = frappe.get_cached_doc("Project Management Settings")

	if task.current_status == "Completed" and not settings.allow_manual_reminder_for_completed:
		frappe.throw(
			_("Task {0} is Completed. Manual reminders for completed tasks are disabled.").format(
				frappe.bold(task.task_name)
			)
		)

	body = (message or "").strip() or build_reminder_message(task)

	link = document_url(document)
	if link:
		body = f"{body}\nView: {link}"

	result = send_whatsapp_message(
		message=body,
		recipient_number=task.concern_person_mobile,
		recipient_name=task.concern_person_name,
		recipient_employee=task.concern_person,
		reminder_type="Manual Reminder",
		project_execution=task.project_execution,
		task_instance=task.name,
		task_name=task.task_name,
		idempotency_key=f"manual::{task.name}::{frappe.utils.now()}",
	)

	# Spec 13: manual reminders do not reset the automatic reminder timer.
	return result


def build_reminder_message(task):
	"""Spec 6.1: automatic task reminder body."""
	latest = frappe.db.get_value(
		"Task Remarks History",
		{"parent": task.name, "parenttype": "Project Task Instance"},
		["remarks", "entry_datetime"],
		order_by="entry_datetime desc",
		as_dict=True,
	)

	lines = [
		f"Hello {task.concern_person_name or ''},".strip(),
		"Please update the progress of your assigned task.",
		f"Project: {frappe.db.get_value('Project Execution', task.project_execution, 'project_title')}",
		f"Task: {task.task_name}",
	]

	if latest:
		lines.append(f"Latest remarks: {latest.remarks}")
		lines.append(f"Last updated: {frappe.utils.format_datetime(latest.entry_datetime, 'd MMMM')}")
	else:
		lines.append("Latest remarks: No update recorded yet.")

	if task.due_date:
		lines.append(f"Due date: {frappe.utils.format_date(task.due_date)}")

	lines.append("Kindly update the latest status and remarks.")
	return "\n".join(lines)
