# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Whitelisted endpoints for the Project Tracker screen (spec sections 4, 5, 9, 10)."""

from urllib.parse import urljoin, urlparse

import frappe
from frappe import _
from frappe.utils import get_url_to_form, now_datetime

from project_management.permissions import can_manage_all_tasks, require_reminder_permission
from project_management.project_management_for_lands_constructions_etc.doctype.project_task_instance.project_task_instance import (
	get_employee_for_user,
)
from project_management.status import COMPLETED, IN_PROGRESS, OPEN
from project_management.whatsapp import send_whatsapp_message


def document_url(document):
	"""Absolute desk URL for the document a WhatsApp message is about.

	`document` is `[doctype, name]` (as the client sends it) or a tuple. Returns an
	empty string when it is missing or malformed, so the caller can fall back.

	WhatsApp only turns a URL into a tappable link when the host looks like a real
	domain; `localhost` and bare IPs arrive as plain text. Project Management
	Settings therefore carries a Public Base URL that replaces the site's own host.
	"""
	if isinstance(document, str):
		document = frappe.parse_json(document)

	if not document or len(document) != 2 or not all(document):
		return ""

	doctype, name = document
	if not frappe.db.exists(doctype, name):
		return ""

	url = get_url_to_form(doctype, name)
	base = (frappe.db.get_single_value("Project Management Settings", "public_base_url") or "").strip()
	if not base:
		return url

	return urljoin(base if base.endswith("/") else base + "/", urlparse(url).path.lstrip("/"))


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
		["project_title", "status"],
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

	# Counted from the rows just read rather than the project's stored counters, so the
	# breakdown can never disagree with the stages rendered beside it.
	completed = len([t for t in tasks if t["current_status"] == COMPLETED])
	in_progress = len([t for t in tasks if t["current_status"] == IN_PROGRESS])

	return {
		"project": project,
		"project_title": execution.project_title,
		"project_status": execution.status,
		"total": len(tasks),
		"completed": completed,
		"in_progress": in_progress,
		"open": len(tasks) - completed - in_progress,
		"tasks": tasks,
	}


@frappe.whitelist()
def get_template_preview(template):
	"""The template's task rows shaped like a pipeline, for the tracker before the
	live project exists. No remarks exist yet, so every stage previews as Open —
	which is exactly the status saving will create it with."""
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
			"current_status": OPEN,
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
		"in_progress": 0,
		"open": len(tasks),
		"tasks": tasks,
	}


@frappe.whitelist()
def send_status_to_admin_master(project, document=None):
	"""Spec 6.2: current project status overview sent to the Admin Master recipients.

	The per-task breakdown is deliberately omitted: the message carries the counts and
	a link to the document, and the recipient reads the detail there."""
	require_reminder_permission()

	pipeline = get_project_pipeline(project)

	lines = [
		"PROJECT STATUS OVERVIEW",
		f"Project: {pipeline['project_title']}",
		f"Project Status: {pipeline['project_status']}",
		f"Total tasks: {pipeline['total']} | Completed: {pipeline['completed']}"
		f" | In Progress: {pipeline['in_progress']} | Open: {pipeline['open']}",
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

	if task.current_status == COMPLETED and not settings.allow_manual_reminder_for_completed:
		frappe.throw(
			_("Task {0} is Completed. Manual reminders for completed tasks are disabled.").format(
				frappe.bold(task.task_name)
			)
		)

	# The typed text is an extra note, not a replacement: the recipient always needs
	# the project, task and latest remark to know what the message is about.
	body = build_reminder_message(task, note=message)

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


def build_reminder_message(task, note=None):
	"""Spec 6.1: task reminder body — project, task, latest remark, due date.

	`note` is the free-text a sender typed in the Manual Task Reminder dialog. It is
	appended, never substituted, so a one-line note still arrives with the project and
	task it refers to.
	"""
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

	note = (note or "").strip()
	if note:
		lines.append(f"Message: {note}")

	lines.append("Kindly update the latest status and remarks.")
	return "\n".join(lines)
