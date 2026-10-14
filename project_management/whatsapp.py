# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Outbound WhatsApp layer (spec sections 8.3 and 9).

Every attempt is logged in WhatsApp Reminder Log with an idempotency key, the
provider message id, attempt time, delivery status and error response. A message
is never reported as delivered merely because an API request was submitted: the
status is taken from the created WhatsApp Message document.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

SENT_STATUSES = ("Success", "sent", "Sent", "delivered", "read", "accepted")


def send_whatsapp_message(
	message,
	recipient_number,
	reminder_type,
	recipient_name=None,
	recipient_employee=None,
	project_execution=None,
	task_instance=None,
	task_name=None,
	idempotency_key=None,
):
	"""Create the log row first, then dispatch. Returns the log as a dict."""
	settings = frappe.get_cached_doc("Project Management Settings")

	# Deduplicate only against a send that actually succeeded or was deliberately
	# skipped. A Failed attempt must stay retryable (spec 12).
	if idempotency_key:
		existing_name = frappe.db.get_value(
			"WhatsApp Reminder Log", {"idempotency_key": idempotency_key}, "name"
		)
		if existing_name:
			existing = frappe.get_doc("WhatsApp Reminder Log", existing_name)
			if existing.delivery_status in ("Sent", "Skipped", "Queued"):
				return _as_result(existing)
			# Retry in place: reuse the row so the key stays unique.
			return _dispatch(existing, message, recipient_number)

	log = frappe.new_doc("WhatsApp Reminder Log")
	log.reminder_type = reminder_type
	log.project_execution = project_execution
	log.task_instance = task_instance
	log.task_name = task_name
	log.recipient_employee = recipient_employee
	log.recipient_name = recipient_name
	log.recipient_number = recipient_number
	log.sent_by = frappe.session.user
	log.attempt_datetime = now_datetime()
	log.message = message
	log.idempotency_key = idempotency_key
	log.delivery_status = "Queued"

	if not settings.enable_whatsapp_reminders:
		log.delivery_status = "Skipped"
		log.skip_reason = "WhatsApp reminders are disabled in Project Management Settings"
		log.insert(ignore_permissions=True)
		return _as_result(log)

	if not recipient_number:
		log.delivery_status = "Skipped"
		log.skip_reason = "Recipient has no WhatsApp number configured"
		log.insert(ignore_permissions=True)
		return _as_result(log)

	log.insert(ignore_permissions=True)

	return _dispatch(log, message, recipient_number)


def _dispatch(log, message, recipient_number):
	"""Create the outbound WhatsApp Message and record the provider outcome.

	Delivery status comes from the created document, not from the fact that an
	API request was submitted (spec 9).
	"""
	try:
		wa = frappe.get_doc(
			{
				"doctype": "WhatsApp Message",
				"type": "Outgoing",
				"message": message,
				"to": recipient_number,
				"content_type": "text",
				"message_type": "Manual",
				"reference_doctype": "WhatsApp Reminder Log",
				"reference_name": log.name,
			}
		).insert(ignore_permissions=True)

		log.db_set(
			{
				"attempt_datetime": now_datetime(),
				"whatsapp_message": wa.name,
				"provider_message_id": wa.message_id,
				"delivery_status": "Sent" if wa.status in SENT_STATUSES else "Failed",
				"error_response": None if wa.status in SENT_STATUSES else json.dumps({"status": wa.status}),
			},
			update_modified=False,
		)
		log.reload()
	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), "Project Management WhatsApp send failed")
		log.db_set(
			{
				"attempt_datetime": now_datetime(),
				"delivery_status": "Failed",
				"error_response": json.dumps({"error": str(exc)}),
			},
			update_modified=False,
		)
		log.reload()

	return _as_result(log)


def _as_result(log):
	return {
		"log": log.name,
		"delivery_status": log.delivery_status,
		"provider_message_id": log.provider_message_id,
		"skip_reason": log.skip_reason,
		"error_response": log.error_response,
	}
