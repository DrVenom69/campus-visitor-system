"""Shared constants. Import from here instead of typing strings in several places."""

ROLES = ("admin", "host", "security", "visitor")
STAFF_ROLES = ("admin", "host", "security")
CREATABLE_ROLES = ("admin", "host", "security")  # roles an admin can create on the Users page

# Status flow: Pending -> Approved -> Checked In -> Checked Out -> Completed
# (or Rejected / Cancelled)
STATUSES = (
    "Pending",
    "Approved",
    "Rejected",
    "Cancelled",
    "Checked In",
    "Checked Out",
    "Completed",
)

PURPOSES = ("Meeting", "Interview", "Delivery", "Event", "Official work", "Other")

PER_PAGE = 15
