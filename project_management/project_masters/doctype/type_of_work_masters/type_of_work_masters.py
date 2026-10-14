# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


# Frappe resolves the controller class as doctype.replace(" ", ""), so the
# class name must be TypeofWorkMasters (lowercase "of") for "Type of Work Masters".
class TypeofWorkMasters(Document):
	def validate(self):
		self.work_name = (self.work_name or "").strip()
		if not self.work_name:
			frappe.throw(_("Work Name is required"))
