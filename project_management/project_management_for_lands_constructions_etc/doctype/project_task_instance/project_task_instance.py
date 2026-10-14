# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate, now_datetime


class ProjectTaskInstance(Document):
	def validate(self):
		self.set_due_date()
		self.sync_reminder_schedule()

	def set_due_date(self):
		"""Spec 13: initial due date = activation/start date + completion timeline (calendar days)."""
		if self.activation_date and self.completion_timeline_in_days:
			self.due_date = add_days(self.activation_date, self.completion_timeline_in_days)

	def sync_reminder_schedule(self):
		"""Spec 8.1: keep last remark, next due, last successful send and state consistent."""
		if self.current_status == "Completed":
			self.next_reminder_due = None
			self.reminder_state = "Disabled"
			if not self.completed_on:
				self.completed_on = now_datetime()
			return

		self.completed_on = None

		if not self.enable_reminders or (self.reminder_in_days or 0) <= 0:
			self.next_reminder_due = None
			self.reminder_state = "Disabled"
			return

		self.next_reminder_due = self.compute_next_reminder_due(self.reminder_anchor())

		if self.reminder_state in (None, "", "Disabled"):
			self.reminder_state = "Scheduled"

	def reminder_anchor(self):
		"""The event the next reminder counts from: the newer of last remark and last send."""
		anchor = get_datetime(self.last_reminder_sent_on) if self.last_reminder_sent_on else None
		remark_on = get_datetime(self.last_remark_on) if self.last_remark_on else None
		if remark_on and (not anchor or remark_on > anchor):
			anchor = remark_on
		return anchor or get_datetime(self.creation or now_datetime())

	def compute_next_reminder_due(self, anchor):
		"""Anchor + Reminder in Days, snapped to midnight.

		Day granularity is deliberate: the dispatch job runs in one fixed hour, so a due
		slot carrying the anchor's clock time would be missed on its own day and the
		interval would drift by a day on every cycle.
		"""
		days = self.reminder_in_days or 0
		return get_datetime(add_days(getdate(anchor), days))

	def sync_tracker_remark(
		self,
		tracker_entry,
		remarks,
		status,
		concern_person=None,
		entry_datetime=None,
		entered_by=None,
	):
		"""Spec 5/6: append one history row per remark, never overwrite an earlier one.

		The table is an audit trail of everything the team wrote on this task. Every
		save that carries a new remark or a new status adds a row recording what was
		written, who wrote it, and whether the status changed; earlier rows — including
		those written through the same tracker entry — stay exactly as they were.

		A save that repeats the most recent remark and status adds nothing, so
		re-saving an unchanged form cannot pad the history.
		"""
		remarks = (remarks or "").strip()
		if not remarks:
			frappe.throw(_("Remarks are required"))

		status = status or self.current_status
		employee = concern_person or get_employee_for_user(frappe.session.user) or self.concern_person

		previous = self.latest_remark()
		if previous and previous.remarks == remarks and previous.status_at_entry == status:
			return self

		previous_status = previous.status_at_entry if previous else None

		self.append(
			"remarks_history",
			{
				"task": self.task,
				"task_name": self.task_name,
				"remarks": remarks,
				"status_at_entry": status,
				"previous_status": previous_status,
				"status_changed": 1 if previous_status and previous_status != status else 0,
				"entry_datetime": get_datetime(entry_datetime) if entry_datetime else now_datetime(),
				"concern_person": employee,
				"concern_person_name": frappe.db.get_value("Employee", employee, "employee_name")
				if employee
				else None,
				"entered_by": entered_by or frappe.session.user,
				"tracker_entry": tracker_entry,
			},
		)

		self.recompute_from_history()
		self.save(ignore_permissions=True)
		return self

	def latest_remark(self):
		"""Most recent history row by entry time, falling back to grid order."""
		history = self.sorted_history()
		return history[-1] if history else None

	def sorted_history(self):
		return sorted(
			self.remarks_history,
			key=lambda r: (
				get_datetime(r.entry_datetime) if r.entry_datetime else datetime.min,
				r.idx or 0,
			),
		)

	def remove_tracker_remark(self, tracker_entry):
		"""Drop history rows written by a tracker entry. Used by migrations only:
		normal saves never retract a remark, they append the next one."""
		remaining = [r for r in self.remarks_history if r.tracker_entry != tracker_entry]

		if len(remaining) == len(self.remarks_history):
			return self

		self.remarks_history = remaining
		for idx, row in enumerate(self.remarks_history, start=1):
			row.idx = idx

		self.recompute_from_history()
		self.save(ignore_permissions=True)
		return self

	def recompute_from_history(self):
		"""Derive current status and last remark time from the latest history row,
		so edits and deletions of tracker entries cannot leave a stale status."""
		latest = self.latest_remark()

		if not latest:
			self.last_remark_on = None
			self.current_status = "WIP"
		else:
			self.last_remark_on = latest.entry_datetime
			if latest.status_at_entry in ("WIP", "Completed"):
				self.current_status = latest.status_at_entry

		if self.current_status == "WIP":
			# A new remark on a WIP task resets the reminder timer (spec 8.1).
			self.reminder_state = "Scheduled"

	def mark_reminder_sent(self, sent_on=None):
		"""Spec 8.1: repeat from last successful send unless a newer remark resets the cycle."""
		sent_on = sent_on or now_datetime()
		self.db_set("last_reminder_sent_on", sent_on, update_modified=False)
		self.db_set("reminder_state", "Sent", update_modified=False)

		anchor = get_datetime(sent_on)
		if self.last_remark_on and get_datetime(self.last_remark_on) > anchor:
			anchor = get_datetime(self.last_remark_on)

		self.db_set(
			"next_reminder_due",
			self.compute_next_reminder_due(anchor),
			update_modified=False,
		)


def get_employee_for_user(user):
	if not user or user == "Administrator":
		return None
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
