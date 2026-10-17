// Copyright (c) 2026, Prajwal k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project Tracker", {
	setup(frm) {
		// Only submitted, enabled templates can produce a live project.
		frm.set_query("project_template", () => {
			return { filters: { docstatus: 1, disabled: 0 } };
		});

		// Spec 4.1: task options come from the live project once it exists, and from
		// the template before that, so the task list is never empty on a new entry.
		frm.set_query("task", () => {
			return {
				query: "project_management.api.tracker_task_query",
				filters: {
					project_execution: frm.doc.project || "",
					project_template: frm.doc.project_template || "",
				},
			};
		});
	},

	refresh(frm) {
		frm.trigger("lock_project_fields");
		frm.trigger("render_pipeline");

		if (frm.is_new()) {
			frm.set_value("status", frm.doc.status || "Open");
			if (!frm.doc.start_date) {
				frm.set_value("start_date", frappe.datetime.get_today());
			}
		}

		if (frm.doc.project) {
			frm.add_custom_button(__("Open Live Project"), () => {
				frappe.set_route("Form", "Project Execution", frm.doc.project);
			});
		}

		frappe.call("project_management.permissions.can_manage_all_tasks").then((r) => {
			if (!r.message) return;

			// Spec 10: both actions are restricted to Admin Master / System Manager.
			frm.add_custom_button(__("Send Status to Admin Master"), () => {
				if (!frm.doc.project) {
					frappe.msgprint(__("Save the entry first to create the live project"));
					return;
				}
				frappe.call({
					method: "project_management.api.send_status_to_admin_master",
					args: {
						project: frm.doc.project,
						// The message links back to the tracker the sender is looking at.
						document: [frm.doctype, frm.doc.name],
					},
					freeze: true,
					freeze_message: __("Sending project status..."),
					callback: (res) => {
						if (res.message) {
							frappe.msgprint({
								title: __("Status Sent"),
								message: res.message.summary,
								indicator: res.message.delivery_status === "Sent" ? "green" : "orange",
							});
						}
					},
				});
			});

			frm.add_custom_button(__("Send Manual Task Reminder"), () => {
				show_manual_reminder_dialog(frm.doc.project, [frm.doctype, frm.doc.name]);
			});
		});
	},

	lock_project_fields(frm) {
		// The live project and its task due dates are derived from these three fields,
		// so after the project exists they are history, not inputs. set_only_once also
		// blocks a change server-side; this makes the form state obvious.
		const locked = !frm.is_new() && !!frm.doc.project;
		["project_template", "project_name", "start_date"].forEach((field) => {
			frm.set_df_property(field, "read_only", locked ? 1 : 0);
		});
		if (locked) {
			// The "will be created on save" hint is about an action that already
			// happened; leaving it up would misdescribe the saved entry.
			frm.set_df_property("project_name", "description", "");
			frm.refresh_field("project_name");
		}
	},

	project_template(frm) {
		frm.set_value("task", null);
		frm.set_value("task_name", null);

		if (!frm.doc.project_template) {
			frm.set_value("project_name", "");
			frm.trigger("render_pipeline");
			return;
		}

		// Default the project name to the template name; the user overrides it to
		// name the actual site or plot.
		if (!frm.doc.project_name) {
			frappe.db.get_value("Project Master Template", frm.doc.project_template, "project_name").then((r) => {
				if (r.message && r.message.project_name) {
					frm.set_value("project_name", r.message.project_name);
				}
			});
		}

		frm.trigger("show_existing_projects");
		frm.trigger("render_pipeline");
	},

	project_name(frm) {
		frm.trigger("show_existing_projects");
	},

	show_existing_projects(frm) {
		// Each tracker creates its own project, so an identical name elsewhere is a
		// collision worth warning about rather than a project to join.
		if (!frm.is_new() || !frm.doc.project_template) {
			frm.set_df_property("project_name", "description", "");
			frm.refresh_field("project_name");
			return;
		}

		frappe.call({
			method: "project_management.api.get_template_projects",
			args: { template: frm.doc.project_template },
			callback: (r) => {
				const rows = r.message || [];
				const typed = (frm.doc.project_name || "").trim();
				const clash = rows.find((row) => row.project_title === typed);

				frm.set_df_property(
					"project_name",
					"description",
					clash
						? __("A project named {0} already exists ({1}). Saving creates a separate one.", [
								typed,
								clash.name,
							])
						: __("A new live project is created on save and owned by this tracker.")
				);
				frm.refresh_field("project_name");
			},
		});
	},

	render_pipeline(frm) {
		const wrapper = frm.get_field("pipeline_html").$wrapper;

		if (frm.doc.project) {
			frappe.call({
				method: "project_management.api.get_project_pipeline",
				args: { project: frm.doc.project },
				callback: (r) => {
					if (r.message) {
						wrapper.html(build_pipeline_html(r.message, frm.doc.task));
					}
				},
			});
			return;
		}

		if (frm.doc.project_template) {
			// No live project yet: preview the template's stages so the user sees what
			// saving will create.
			frappe.call({
				method: "project_management.api.get_template_preview",
				args: { template: frm.doc.project_template },
				callback: (r) => {
					if (r.message) {
						wrapper.html(build_pipeline_html(r.message, frm.doc.task));
					}
				},
			});
			return;
		}

		wrapper.html(
			`<div class="text-muted" style="padding:12px">${__("Select a project template to view its tasks")}</div>`
		);
	},

	task(frm) {
		// Start from the task's current status so saving a remark cannot silently
		// reopen a Completed task or hide that work is already under way.
		if (frm.doc.project && frm.doc.task) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Project Task Instance",
					filters: { project_execution: frm.doc.project, task: frm.doc.task },
					fieldname: ["current_status"],
				},
				callback: (r) => {
					if (r.message && r.message.current_status) {
						frm.set_value("status", r.message.current_status);
					}
				},
			});
		}
		frm.trigger("render_pipeline");
	},

	after_save(frm) {
		// Spec 4.2: refresh the pipeline after a successful save; the project now exists.
		frm.trigger("lock_project_fields");
		frm.trigger("render_pipeline");
	},
});

function build_pipeline_html(data, active_task) {
	const esc = frappe.utils.escape_html;
	const color = { Completed: "green", "In Progress": "blue", Open: "orange" };
	const project_color = {
		Completed: "green",
		"In Progress": "blue",
		Open: "orange",
		"On Hold": "yellow",
		Cancelled: "red",
		"Not Created": "gray",
	};

	let html = `<div class="pm-pipeline">
		<div class="pm-pipeline-head">
			<b>${esc(data.project_title)}</b>
			<span class="indicator-pill ${project_color[data.project_status] || "gray"}">${esc(
				data.project_status || ""
			)}</span>
			<span class="text-muted"> — ${data.completed}/${data.total} ${__("completed")}</span>
		</div>`;

	data.tasks.forEach((task) => {
		const is_active = task.task === active_task;
		html += `<div class="pm-stage${is_active ? " pm-stage-active" : ""}">
			<div class="pm-stage-head">
				<span class="pm-stage-title">${task.sequence}. ${esc(task.task_name)}</span>
				<span class="indicator-pill ${color[task.current_status] || "gray"}">${esc(task.current_status)}</span>
			</div>
			<div class="text-muted pm-stage-meta">${esc(task.concern_person_name || "")}${
				task.due_date ? " · " + __("Due") + " " + frappe.datetime.str_to_user(task.due_date) : ""
			}</div>`;

		if (task.remarks && task.remarks.length) {
			// Newest first: the latest update is what a reader needs, so it leads and is
			// the only bold entry; older remarks stay as plain context below it.
			html += `<ul class="pm-remarks">`;
			task.remarks
				.slice()
				.reverse()
				.forEach((rm, index) => {
					const changed =
						rm.status_changed && rm.previous_status
							? ` · ${esc(rm.previous_status)} → ${esc(rm.status_at_entry)}`
							: "";
					html += `<li class="${index === 0 ? "pm-remark-latest" : ""}">
					<div class="pm-remark-text">${esc(rm.remarks)}</div>
					<div class="text-muted pm-remark-meta">${esc(rm.concern_person_name || rm.entered_by || "")} | ${
						frappe.datetime.str_to_user(rm.entry_datetime, true) || ""
					}${changed}</div>
				</li>`;
				});
			html += `</ul>`;
		} else {
			html += `<div class="text-muted pm-remarks-empty">${__("No remarks yet")}</div>`;
		}

		html += `</div>`;
	});

	html += `</div>`;
	return html;
}

function show_manual_reminder_dialog(default_project, document) {
	// Spec Screen 5: Manual Task Reminder dialog.
	const d = new frappe.ui.Dialog({
		title: __("Send Manual Task Reminder"),
		fields: [
			{
				fieldname: "project",
				fieldtype: "Link",
				label: __("Project"),
				options: "Project Execution",
				reqd: 1,
				default: default_project,
				onchange() {
					d.set_value("task_instance", "");
					d.set_value("recipient", "");
				},
			},
			{
				fieldname: "task_instance",
				fieldtype: "Link",
				label: __("Task"),
				options: "Project Task Instance",
				reqd: 1,
				get_query() {
					return {
						query: "project_management.api.task_instance_query",
						filters: { project_execution: d.get_value("project") || "" },
					};
				},
				onchange() {
					const task = d.get_value("task_instance");
					if (!task) return;
					frappe.db.get_value(
						"Project Task Instance",
						task,
						["concern_person_name", "concern_person_mobile", "current_status"],
						(v) => {
							d.set_value(
								"recipient",
								`${v.concern_person_name || ""} ${v.concern_person_mobile ? "(" + v.concern_person_mobile + ")" : ""}`
							);
							d.set_df_property(
								"status_warning",
								"options",
								v.current_status === "Completed"
									? `<div class="text-danger">${__("This task is Completed; manual reminders are disabled by default.")}</div>`
									: ""
							);
						}
					);
				},
			},
			{
				fieldname: "message",
				fieldtype: "Small Text",
				label: __("Additional Message"),
				description: __(
					"Optional. Added to the reminder, which always carries the project, task and latest remarks."
				),
			},
			{
				fieldname: "recipient",
				fieldtype: "Data",
				label: __("Recipient"),
				read_only: 1,
				description: __("Assigned Concern Person (auto)"),
			},
			{ fieldname: "status_warning", fieldtype: "HTML" },
		],
		primary_action_label: __("Send Reminder"),
		primary_action(values) {
			frappe.call({
				method: "project_management.api.send_manual_task_reminder",
				args: {
					task_instance: values.task_instance,
					message: values.message,
					document: document,
				},
				freeze: true,
				freeze_message: __("Sending reminder..."),
				callback: (r) => {
					if (r.message) {
						d.hide();
						frappe.show_alert({
							message: __("Reminder {0}", [r.message.delivery_status]),
							indicator: r.message.delivery_status === "Sent" ? "green" : "orange",
						});
					}
				},
			});
		},
	});
	d.show();
}
