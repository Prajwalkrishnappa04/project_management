// Copyright (c) 2026, Prajwal k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project Master Template", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && !frm.doc.disabled) {
			frm.add_custom_button(__("Create Live Project"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Create Live Project"),
					fields: [
						{
							fieldname: "project_title",
							fieldtype: "Data",
							label: __("Project Title"),
							reqd: 1,
							default: frm.doc.project_name,
						},
						{
							fieldname: "start_date",
							fieldtype: "Date",
							label: __("Start Date"),
							reqd: 1,
							default: frappe.datetime.get_today(),
						},
					],
					primary_action_label: __("Create"),
					primary_action(values) {
						frm.call("create_project_execution", values).then((r) => {
							if (r.message) {
								d.hide();
								frappe.set_route("Form", "Project Execution", r.message);
							}
						});
					},
				});
				d.show();
			}).addClass("btn-primary");
		}
	},
});

frappe.ui.form.on("Project Task Detail", {
	enable_reminders(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.enable_reminders) {
			frappe.model.set_value(cdt, cdn, "reminder_in_days", 0);
		} else if (!row.reminder_in_days) {
			frappe.model.set_value(cdt, cdn, "reminder_in_days", 7);
		}
	},
});
