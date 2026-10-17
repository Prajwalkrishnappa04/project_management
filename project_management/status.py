# Copyright (c) 2026, Prajwal k and contributors
# For license information, please see license.txt
"""The task status lifecycle, in one place.

A task instance starts **Open**. Writing a remark on it means the work has started,
so the first remark moves it to **In Progress** automatically — nobody has to set
that by hand. **Completed** is never derived: it is only reached because a person
chose it on the Project Tracker entry.
"""

OPEN = "Open"
IN_PROGRESS = "In Progress"
COMPLETED = "Completed"

TASK_STATUSES = (OPEN, IN_PROGRESS, COMPLETED)

#: Statuses of a task that is still being worked on — reminders apply to these.
PENDING_STATUSES = (OPEN, IN_PROGRESS)


#: A project carries the same three phases as its tasks, plus the two manual
#: interventions that progress must never override.
ON_HOLD = "On Hold"
CANCELLED = "Cancelled"

PROJECT_STATUSES = (OPEN, IN_PROGRESS, COMPLETED, ON_HOLD, CANCELLED)

#: Statuses a progress recalculation must leave alone: somebody set them by hand.
MANUAL_PROJECT_STATUSES = (ON_HOLD, CANCELLED)


def status_for_remark(status):
	"""The status a task carries once a remark is written on it.

	An Open task (or a blank status) is promoted to In Progress, because a remark is
	evidence the work started. In Progress and Completed are passed through: a chosen
	Completed must not be downgraded, and an In Progress task stays where it is.
	"""
	if status in (None, "", OPEN):
		return IN_PROGRESS
	return status
