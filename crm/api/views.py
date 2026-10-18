import frappe
from pypika import Criterion


@frappe.whitelist()
def get_views(doctype: str):
	View = frappe.qb.DocType("CRM View Settings")
	query = (
		frappe.qb.from_(View)
		.select("*")
		.where(Criterion.any([View.user == "", View.user == frappe.session.user]))
	)
	if doctype:
		query = query.where(View.dt == doctype)
	views = query.run(as_dict=True)
	return views


@frappe.whitelist(methods=["POST"])
def set_kanban_background(doctype: str, background: str | None = None, view: str | None = None):
	"""Trello-style board background for the user's kanban view of `doctype` (or the named
	custom view): "#rrggbb", "g:<preset>" or an image URL. Empty clears it."""
	import re

	from crm.fcrm.doctype.crm_view_settings.crm_view_settings import create_or_update_standard_view

	background = (background or "").strip() or None
	if background and not (
		re.fullmatch(r"#[0-9a-fA-F]{6}", background)
		or re.fullmatch(r"g:[a-z]+", background)
		or background.startswith(("/files/", "https://"))
	):
		frappe.throw(frappe._("Use a colour, a preset or an image URL."))
	if view:
		owner = frappe.db.get_value("CRM View Settings", view, "user")
		if owner != frappe.session.user and "System Manager" not in frappe.get_roles():
			frappe.throw(frappe._("You can only change your own views."), frappe.PermissionError)
		name = view
	else:
		name = frappe.db.get_value(
			"CRM View Settings",
			{"dt": doctype, "type": "kanban", "is_standard": 1, "user": frappe.session.user},
		)
		if not name:
			name = create_or_update_standard_view({"type": "kanban", "doctype": doctype}).name
	frappe.db.set_value("CRM View Settings", name, "kanban_background", background)
	return background
