import frappe
from frappe import _


@frappe.whitelist()
def get_options(doctype: str, status: str | None = None, name: str | None = None) -> dict:
	"""What the lost-reason dialog shows for a move to `status` (a status of type Lost, e.g. Lost or Junk).

	Apps can tailor it with the hook `crm_lost_reason_options = ["dotted.path"]`: each is called with (doctype, status, name)
	and may return a dict that is merged in order: title, message, field_label, reasons (a list of CRM Lost Reason names to offer
	instead of all), allow_create, and assist ({label, method}: a button that calls method with doctype, name, status,
	reasons and notes and fills in the lost_reason / lost_notes it returns).
	"""
	if name:
		frappe.has_permission(doctype, "write", name, throw=True)
	label = (doctype or "").lower().replace("crm ", "")
	options = {
		"title": _("Lost Reason"),
		"field_label": _("Lost Reason"),
		"message": _("Please provide a reason for marking this {0} as lost").format(label),
		"reasons": None,
		"allow_create": True,
		"assist": None,
	}
	for path in frappe.get_hooks("crm_lost_reason_options"):
		extra = frappe.get_attr(path)(doctype=doctype, status=status, name=name)
		if extra:
			options.update(extra)
	return options
