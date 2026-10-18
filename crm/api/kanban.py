import frappe


@frappe.whitelist()
def get_move_dialog(doctype: str, name: str, fieldname: str, from_value: str | None = None, to_value: str | None = None):
	"""Ask installed apps whether moving a kanban card needs input first.

	Apps register `crm_kanban_move_dialog = ["dotted.path"]` in their hooks. Each is called with
	(doctype, name, fieldname, from_value, to_value); the first that returns a dict wins. The dict is
	a form dialog spec (title, fields, defaults, required, submitLabel) plus `submit_method` and
	`submit_args`: the board calls submit_method with submit_args and the dialog's values, then saves
	the move. None (no app objects) keeps the board's plain behaviour.
	"""
	frappe.has_permission(doctype, "write", name, throw=True)
	for path in frappe.get_hooks("crm_kanban_move_dialog"):
		spec = frappe.get_attr(path)(
			doctype=doctype, name=name, fieldname=fieldname, from_value=from_value, to_value=to_value
		)
		if spec:
			return spec
	return None
