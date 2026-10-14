# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ProjectManagementSettings(Document):
	def get_status_recipients(self):
		"""Recipients for Send Status to Admin Master (spec 6.2)."""
		recipients = []
		for row in self.status_recipients:
			if not row.enabled or not row.mobile_number:
				continue
			recipients.append(
				{
					"employee": row.employee,
					"name": row.recipient_name,
					"number": row.mobile_number,
				}
			)
		return recipients
