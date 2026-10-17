# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Reminder scheduler (spec section 8).

Rules implemented here:
- the interval is read from the task instance (copied from Project Master); never hardcoded;
- before sending, the task is reloaded and skipped unless it is still Open or In Progress;
- the next reminder is computed from the latest remark if one is newer than the last send;
- a deduplication key per task and due slot prevents duplicate sends on retry;
- dispatch runs in a background job so a user's Save is never blocked.
"""

import frappe
from frappe.utils import now_datetime

from project_management.status import PENDING_STATUSES
from project_management.whatsapp import send_whatsapp_message


def send_due_reminders():
	"""Daily scheduler entry point: find due reminders and enqueue dispatch."""
	settings = frappe.get_cached_doc("Project Management Settings")
	if not settings.enable_whatsapp_reminders:
		return

	# 0 is a valid hour, so test for "configured" and not for truthiness.
	send_hour = settings.reminder_send_hour
	if send_hour not in (None, "") and now_datetime().hour != int(send_hour):
		return

	due = frappe.get_all(
		"Project Task Instance",
		filters={
			"current_status": ["in", PENDING_STATUSES],
			"enable_reminders": 1,
			"next_reminder_due": ["<=", now_datetime()],
		},
		pluck="name",
	)

	for name in due:
		# Spec 8.3: never block on the provider; dispatch each task in the background queue.
		frappe.enqueue(
			"project_management.tasks.dispatch_reminder",
			queue="long",
			job_id=f"pm-reminder::{name}",
			deduplicate=True,
			task_instance=name,
		)


def dispatch_reminder(task_instance):
	"""Send one reminder after re-checking the task's live state (spec 8.1)."""
	from project_management.api import build_reminder_message

	task = frappe.get_doc("Project Task Instance", task_instance)

	# Recheck immediately before dispatch: the task may have been completed
	# after the scheduler selected it.
	if task.current_status not in PENDING_STATUSES:
		task.db_set("reminder_state", "Skipped", update_modified=False)
		task.db_set("next_reminder_due", None, update_modified=False)
		_log_skip(task, f"Task is {task.current_status}; reminders apply to open work only")
		return

	if not task.enable_reminders or (task.reminder_in_days or 0) <= 0:
		task.db_set("reminder_state", "Disabled", update_modified=False)
		task.db_set("next_reminder_due", None, update_modified=False)
		_log_skip(task, "Reminders disabled for this task")
		return

	# Repeat from the later of the last successful send and the last remark (spec 8.1):
	# anchoring only on the remark would freeze the due slot and suppress every repeat.
	due = task.compute_next_reminder_due(task.reminder_anchor())

	# A remark or send after the scheduler ran restarts the cycle instead of sending.
	if due > now_datetime():
		task.db_set("next_reminder_due", due, update_modified=False)
		task.db_set("reminder_state", "Scheduled", update_modified=False)
		return

	result = send_whatsapp_message(
		message=build_reminder_message(task),
		recipient_number=task.concern_person_mobile,
		recipient_name=task.concern_person_name,
		recipient_employee=task.concern_person,
		reminder_type="Automatic Reminder",
		project_execution=task.project_execution,
		task_instance=task.name,
		task_name=task.task_name,
		# Spec 8.3: one send per task per due slot, even if the job is retried.
		idempotency_key=f"auto::{task.name}::{due.strftime('%Y-%m-%d')}",
	)

	if result["delivery_status"] == "Sent":
		task.mark_reminder_sent()
	elif result["delivery_status"] == "Skipped":
		task.db_set("reminder_state", "Skipped", update_modified=False)
	else:
		task.db_set("reminder_state", "Failed", update_modified=False)


def _log_skip(task, reason):
	log = frappe.new_doc("WhatsApp Reminder Log")
	log.reminder_type = "Automatic Reminder"
	log.project_execution = task.project_execution
	log.task_instance = task.name
	log.task_name = task.task_name
	log.recipient_employee = task.concern_person
	log.recipient_name = task.concern_person_name
	log.recipient_number = task.concern_person_mobile
	log.attempt_datetime = now_datetime()
	log.delivery_status = "Skipped"
	log.skip_reason = reason
	log.insert(ignore_permissions=True)
