# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WhatsAppReminderLog(Document):
	"""Records every outbound WhatsApp attempt: payload, provider id, delivery status,
	skip reason and error response (spec 8.3)."""

	pass
