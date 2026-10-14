# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""Post-install / post-migrate setup: roles required by the permission matrix (spec 10)."""

import frappe

ROLES = (
	{"role_name": "Admin Master", "desk_access": 1},
	{"role_name": "Concern Person", "desk_access": 1},
)


def after_install():
	create_roles()
	ensure_settings()


def create_roles():
	for role in ROLES:
		if frappe.db.exists("Role", role["role_name"]):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role["role_name"],
				"desk_access": role["desk_access"],
			}
		).insert(ignore_permissions=True)


def ensure_settings():
	if not frappe.db.exists("DocType", "Project Management Settings"):
		return
	settings = frappe.get_single("Project Management Settings")
	if not settings.get("default_reminder_in_days"):
		settings.default_reminder_in_days = 7
		settings.reminder_send_hour = 9
		settings.enable_whatsapp_reminders = 1
		settings.save(ignore_permissions=True)
