# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TaskMaster(Document):
	def validate(self):
		self.task_master = (self.task_master or "").strip()
		if not self.task_master:
			frappe.throw(_("Task Master is required"))
