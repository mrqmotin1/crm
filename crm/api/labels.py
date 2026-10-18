"""Trello-style labels on leads and deals.

A label is a CRM Label (name + colour). A lead or deal keeps its labels as a JSON list of
names in its `labels` field, so list and kanban views read them without a join. Renaming
or deleting a label rewrites that list on every document that has it.
"""

import json

import frappe
from frappe import _

DOCTYPES = ("CRM Lead", "CRM Deal")
COLORS = ("green", "yellow", "orange", "red", "purple", "blue", "sky", "lime", "pink", "gray", "black")


def _parse(value) -> list[str]:
	if not value:
		return []
	try:
		names = json.loads(value)
	except ValueError:
		return []
	return [n for n in names if isinstance(n, str)]


@frappe.whitelist()
def get_labels() -> list[dict]:
	return frappe.get_all("CRM Label", fields=["name", "label", "color"], order_by="label asc")


@frappe.whitelist(methods=["POST"])
def set_labels(doctype: str, name: str, labels) -> list[str]:
	"""Replace the labels on one lead/deal. Leaves `modified` alone, so an open form
	can still save afterwards."""
	if doctype not in DOCTYPES:
		frappe.throw(_("Labels are only for leads and deals."))
	frappe.has_permission(doctype, "write", name, throw=True)
	if isinstance(labels, str):
		labels = json.loads(labels or "[]")
	known = set(frappe.get_all("CRM Label", pluck="name"))
	clean = []
	for label in labels or []:
		if label in known and label not in clean:
			clean.append(label)
	frappe.db.set_value(doctype, name, "labels", json.dumps(clean) if clean else None, update_modified=False)
	return clean


@frappe.whitelist(methods=["POST"])
def save_label(label: str, color: str = "green", name: str | None = None) -> dict:
	"""Create a label, or rename/recolour `name`."""
	label = (label or "").strip()
	if not label:
		frappe.throw(_("A label needs a name."))
	if color not in COLORS:
		color = "green"
	if not name:
		frappe.has_permission("CRM Label", "create", throw=True)
		doc = frappe.get_doc({"doctype": "CRM Label", "label": label, "color": color}).insert()
		return {"name": doc.name, "label": doc.label, "color": doc.color}

	frappe.has_permission("CRM Label", "write", name, throw=True)
	doc = frappe.get_doc("CRM Label", name)
	doc.color = color
	if label != name:
		if frappe.db.exists("CRM Label", label):
			frappe.throw(_("A label called {0} already exists.").format(label))
		doc.label = label
		doc.save()
		frappe.rename_doc("CRM Label", name, label, force=True)
		_rewrite(name, label)
	else:
		doc.save()
	return {"name": label, "label": label, "color": color}


@frappe.whitelist(methods=["POST"])
def delete_label(name: str):
	frappe.has_permission("CRM Label", "delete", name, throw=True)
	_rewrite(name, None)
	frappe.delete_doc("CRM Label", name)


def _rewrite(old: str, new: str | None):
	"""Rename (new) or remove (None) a label on every lead and deal that has it."""
	needle = f"%{json.dumps(old)}%"
	for dt in DOCTYPES:
		for row in frappe.get_all(dt, filters={"labels": ("like", needle)}, fields=["name", "labels"]):
			names = [new if n == old else n for n in _parse(row.labels)]
			names = [n for i, n in enumerate(names) if n and n not in names[:i]]
			frappe.db.set_value(dt, row.name, "labels", json.dumps(names) if names else None, update_modified=False)
