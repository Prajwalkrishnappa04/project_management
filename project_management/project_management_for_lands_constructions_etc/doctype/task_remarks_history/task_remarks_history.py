# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TaskRemarksHistory(Document):
	"""Append-only remark history. Rows are written by the server only; see
	Project Task Instance.append_remark(). Author and timestamp are read-only (spec 5)."""

	pass
