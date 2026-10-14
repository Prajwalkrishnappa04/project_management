# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Role and row-level permission rules (spec section 10).

Concern Person sees only assigned tasks; Admin Master and System Manager see all.
Button visibility is never treated as authorization; every restricted action calls
require_reminder_permission() on the server.
"""

import frappe
from frappe import _

ELEVATED_ROLES = ("Admin Master", "System Manager", "Administrator")


@frappe.whitelist()
def can_manage_all_tasks(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	return bool(roles.intersection(ELEVATED_ROLES))


def require_reminder_permission(user=None):
	"""Server-side gate for Send Status to Admin Master and Send Manual Task Reminder."""
	if not can_manage_all_tasks(user):
		frappe.throw(
			_("Only Admin Master and System Manager can send WhatsApp reminders"),
			frappe.PermissionError,
		)


def get_employee(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return None
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def task_instance_query_conditions(user=None):
	"""permission_query_conditions for Project Task Instance list/report views."""
	if can_manage_all_tasks(user):
		return ""

	employee = get_employee(user)
	if not employee:
		return "1=0"

	return f"`tabProject Task Instance`.`concern_person` = {frappe.db.escape(employee)}"


def has_task_instance_permission(doc, ptype=None, user=None):
	if can_manage_all_tasks(user):
		return True

	employee = get_employee(user)
	if not employee:
		return False

	return doc.concern_person == employee


def tracker_query_conditions(user=None):
	"""permission_query_conditions for Project Tracker: own entries only."""
	if can_manage_all_tasks(user):
		return ""

	employee = get_employee(user)
	if not employee:
		return "1=0"

	return f"`tabProject Tracker`.`concern_person` = {frappe.db.escape(employee)}"


def has_tracker_permission(doc, ptype=None, user=None):
	if can_manage_all_tasks(user):
		return True

	employee = get_employee(user)
	if not employee:
		return False

	# A new entry has no concern_person yet (the controller fills it in validate), so
	# judging it by that field would deny every Concern Person the right to create one.
	if not doc.get("name") or doc.get("__islocal"):
		return True

	return doc.concern_person == employee
