"""WhatsApp inbox: every chat on our WhatsApp numbers in one place, linked or not.

One CRM WhatsApp Conversation per (WhatsApp Account, customer number), kept up to date from WhatsApp Message (frappe_whatsapp)
in `track_message` (called from crm.api.whatsapp.validate). Each message points at its conversation through the custom
field `crm_conversation`. A reply always leaves from the number the customer wrote to.

Visibility: sales managers see every conversation; a sales user sees the ones they own and the unowned ones that are
unlinked or shared with them (assigned on the linked record).
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime, strip_html

SALES_ROLES = {"System Manager", "Sales Manager", "Sales User"}
MANAGER_ROLES = {"System Manager", "Sales Manager"}
WINDOW_HOURS = 24  # Meta's customer service window: free-form replies only within 24 h of the customer's last message
FIELD = "crm_conversation"


# ---------------------------------------------------------------- setup


def ensure_fields():
	"""The link from WhatsApp Message to its conversation (custom field, since the doctype belongs to frappe_whatsapp)."""
	if not frappe.db.exists("DocType", "WhatsApp Message"):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	if not frappe.db.exists("Custom Field", {"dt": "WhatsApp Message", "fieldname": FIELD}):
		create_custom_field(
			"WhatsApp Message",
			{
				"fieldname": FIELD,
				"label": "CRM Conversation",
				"fieldtype": "Link",
				"options": "CRM WhatsApp Conversation",
				"insert_after": "whatsapp_account",
				"read_only": 1,
				"search_index": 1,
			},
		)


def after_migrate():
	ensure_fields()
	backfill()


def after_app_install(app_name):
	if app_name == "frappe_whatsapp":
		ensure_fields()
		from crm.api.whatsapp import add_roles

		add_roles()


def backfill(limit: int = 5000):
	"""Conversations for messages stored before the inbox existed (oldest first, so the latest one sets the summary)."""
	if not frappe.db.exists("DocType", "WhatsApp Message") or not has_field():
		return
	names = frappe.get_all(
		"WhatsApp Message",
		filters={FIELD: ("is", "not set"), "content_type": ("!=", "reaction")},
		pluck="name",
		order_by="creation asc",
		limit=limit,
	)
	for name in names:
		doc = frappe.get_doc("WhatsApp Message", name)
		conversation = track_message(doc, at=doc.creation)
		if conversation:
			frappe.db.set_value("WhatsApp Message", name, FIELD, conversation, update_modified=False)


def has_field() -> bool:
	return bool(frappe.get_meta("WhatsApp Message").has_field(FIELD))


# ---------------------------------------------------------------- numbers


def _default_region() -> str:
	country = frappe.db.get_default("country")
	code = country and frappe.db.get_value("Country", country, "code")
	return (code or "IN").upper()


def normalize_number(number) -> str:
	"""Digits in international form without '+' (what Meta uses): '+880 1712-345678', '01712345678' and '8801712345678'
	all become '8801712345678'. A local number takes the system country's code."""
	from crm.utils import parse_phone_number

	raw = str(number or "").strip()
	digits = re.sub(r"\D", "", raw)
	if not digits:
		return ""
	if digits.startswith("00"):
		digits = digits[2:]
	tries = [(raw, _default_region())]
	if raw.startswith("+") or raw.startswith("00") or len(digits) > 11:
		tries.insert(0, ("+" + digits, "IN"))  # already international; the region is ignored
	for candidate, region in tries:
		parsed = parse_phone_number(candidate, region)
		if parsed.get("success") and parsed.get("is_valid"):
			return parsed["formats"]["E164"].lstrip("+")
	return digits


# ---------------------------------------------------------------- tracking (from crm.api.whatsapp.validate)


def _owner_of(doctype, name):
	if not doctype or not name:
		return None
	field = {"CRM Lead": "lead_owner", "CRM Deal": "deal_owner"}.get(doctype)
	return frappe.db.get_value(doctype, name, field) if field else None


def get_or_create(account: str, number: str, profile_name: str | None = None) -> "frappe.model.document.Document":
	name = frappe.db.get_value("CRM WhatsApp Conversation", {"whatsapp_account": account, "contact_number": number})
	if name:
		return frappe.get_doc("CRM WhatsApp Conversation", name)
	conversation = frappe.new_doc("CRM WhatsApp Conversation")
	conversation.update({"whatsapp_account": account, "contact_number": number, "profile_name": profile_name, "status": "Open"})
	conversation.insert(ignore_permissions=True)
	return conversation


def track_message(doc, at=None) -> str | None:
	"""Update (or start) the message's conversation and point the message at it. Returns the conversation name."""
	if doc.get("content_type") == "reaction":
		return None
	incoming = doc.type == "Incoming"
	number = normalize_number(doc.get("from") if incoming else doc.get("to"))
	account = doc.get("whatsapp_account")
	if not number or not account:
		return None

	conversation = get_or_create(account, number, doc.get("profile_name") if incoming else None)
	at = at or now_datetime()
	text = doc.get("message") or ""
	if doc.get("message_type") == "Template":
		text = _("Template: {0}").format(doc.get("template") or "")
	elif doc.get("content_type") not in (None, "", "text", "button"):
		text = f"[{doc.get('content_type')}] " + ("" if text.startswith("/files/") else text)

	values = {
		"last_message": strip_html(text)[:280],
		"last_direction": doc.type,
		"last_message_at": at,
	}
	if incoming:
		values.update(
			{
				"last_incoming_at": at,
				"unread": cint(conversation.unread) + 1,
				"status": "Open",
			}
		)
		if doc.get("profile_name"):
			values["profile_name"] = doc.profile_name
	else:
		values["unread"] = 0
	if doc.get("reference_doctype") and doc.get("reference_name"):
		values.update(
			{
				"reference_doctype": doc.reference_doctype,
				"reference_name": doc.reference_name,
				"owner_user": _owner_of(doc.reference_doctype, doc.reference_name),
			}
		)
	conversation.db_set(values, update_modified=False)
	if has_field():
		doc.set(FIELD, conversation.name)
	return conversation.name


def publish(conversation: str | None):
	if conversation:
		frappe.publish_realtime("whatsapp_inbox", {"conversation": conversation}, after_commit=True)


def on_record_owner_change(doc, method=None):
	"""Lead/Deal owner changed: keep its conversations' owner in step (the inbox's Mine / Unassigned filters)."""
	field = {"CRM Lead": "lead_owner", "CRM Deal": "deal_owner"}.get(doc.doctype)
	if not field or not doc.has_value_changed(field) or not frappe.db.exists("DocType", "CRM WhatsApp Conversation"):
		return
	names = frappe.get_all(
		"CRM WhatsApp Conversation",
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("CRM WhatsApp Conversation", name, "owner_user", doc.get(field), update_modified=False)
		publish(name)


def account_for(reference_doctype=None, reference_name=None, number=None) -> str | None:
	"""The number the customer last wrote to (so a reply leaves from it), else None (frappe_whatsapp's default)."""
	filters = []
	if reference_doctype and reference_name:
		filters.append({"reference_doctype": reference_doctype, "reference_name": reference_name})
	number = normalize_number(number)
	if number:
		filters.append({"contact_number": number})
	for f in filters:
		account = frappe.db.get_value(
			"CRM WhatsApp Conversation", f, "whatsapp_account", order_by="last_incoming_at desc, last_message_at desc"
		)
		if account:
			return account
	return None


# ---------------------------------------------------------------- access


def _check_role():
	if not SALES_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Only sales users can access WhatsApp."), frappe.PermissionError)


def _is_manager(user=None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(MANAGER_ROLES & set(frappe.get_roles(user)))


def _shared_with(row, user) -> bool:
	if not row.reference_doctype or not row.reference_name:
		return True
	assigned = frappe.db.get_value(row.reference_doctype, row.reference_name, "_assign") or "[]"
	try:
		return user in json.loads(assigned)
	except ValueError:
		return False


def can_see(row, user=None) -> bool:
	user = user or frappe.session.user
	if _is_manager(user):
		return True
	if row.owner_user:
		return row.owner_user == user
	return _shared_with(row, user)


def _get(conversation: str, permtype: str = "read"):
	_check_role()
	if not frappe.db.exists("CRM WhatsApp Conversation", conversation):
		frappe.throw(_("Conversation not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("CRM WhatsApp Conversation", conversation)
	if not can_see(doc):
		frappe.throw(_("Not permitted to see this conversation."), frappe.PermissionError)
	if permtype == "write" and doc.reference_doctype and doc.reference_name:
		from crm.api.whatsapp import validate_access

		validate_access(doc.reference_doctype, doc.reference_name)
	return doc


def window_open(last_incoming_at) -> bool:
	return bool(last_incoming_at) and get_datetime(last_incoming_at) > add_to_date(now_datetime(), hours=-WINDOW_HOURS)


def can_send(account: str | None) -> bool:
	"""Sending needs the account's access token; without one the number is receive-only."""
	if not account:
		return False
	return bool(
		frappe.db.exists("__Auth", {"doctype": "WhatsApp Account", "name": account, "fieldname": "token"})
	)


# ---------------------------------------------------------------- API


def _rows(scope="all", unread=0, search=None, account=None, status="Open", start=0, limit=50):
	user = frappe.session.user
	conditions, values = [], {}
	if status in ("Open", "Done"):
		conditions.append("c.status = %(status)s")
		values["status"] = status
	if account:
		conditions.append("c.whatsapp_account = %(account)s")
		values["account"] = account
	if cint(unread):
		conditions.append("c.unread > 0")
	if search:
		conditions.append(
			"(c.profile_name like %(q)s or c.contact_number like %(q)s or c.reference_name like %(q)s"
			" or c.last_message like %(q)s)"
		)
		values["q"] = f"%{search.strip()}%"
	if scope == "mine":
		conditions.append("c.owner_user = %(user)s")
	elif scope == "unassigned":
		conditions.append("ifnull(c.owner_user, '') = ''")
	if not _is_manager(user):
		conditions.append("(c.owner_user = %(user)s or ifnull(c.owner_user, '') = '')")
	values["user"] = user
	where = " and ".join(conditions) or "1=1"
	# over-fetch a little: unowned rows are checked against the record's assignments below
	rows = frappe.db.sql(
		f"""select c.name, c.profile_name, c.contact_number, c.whatsapp_account, c.reference_doctype,
			c.reference_name, c.owner_user, c.last_message, c.last_direction, c.last_message_at,
			c.last_incoming_at, c.unread, c.status
		from `tabCRM WhatsApp Conversation` c where {where}
		order by c.last_message_at desc limit %(limit)s offset %(start)s""",
		{**values, "limit": cint(limit) * 2 + 10, "start": cint(start)},
		as_dict=True,
	)
	return [r for r in rows if can_see(r, user)][: cint(limit)]


@frappe.whitelist()
def list_conversations(scope="all", unread=0, search=None, account=None, status="Open", start=0, limit=50):
	_check_role()
	rows = _rows(scope, unread, search, account, status, start, limit)
	accounts = {}
	for row in rows:
		acc = row.whatsapp_account
		if acc not in accounts:
			accounts[acc] = frappe.db.get_value("WhatsApp Account", acc, "account_name") if acc else None
		row.account_label = accounts[acc] or acc
		row.window_open = window_open(row.last_incoming_at)
		row.reference_title, row.reference_status = None, None
		if row.reference_doctype in ("CRM Lead", "CRM Deal") and row.reference_name:
			title_field = "lead_name" if row.reference_doctype == "CRM Lead" else "organization"
			t = frappe.db.get_value(row.reference_doctype, row.reference_name, [title_field, "status"], as_dict=True)
			if t:
				row.reference_title, row.reference_status = t.get(title_field), t.status
		elif row.reference_doctype == "Contact" and row.reference_name:
			row.reference_title = frappe.db.get_value("Contact", row.reference_name, "full_name") or row.reference_name
			row.reference_status = _("Contact")
	return rows


@frappe.whitelist()
def unread_count() -> int:
	if not SALES_ROLES & set(frappe.get_roles()):
		return 0
	if not frappe.db.exists("DocType", "CRM WhatsApp Conversation"):
		return 0
	return sum(1 for r in _rows(unread=1, limit=200) if r.unread)


@frappe.whitelist()
def get_conversation(conversation: str):
	doc = _get(conversation)
	out = doc.as_dict()
	out.account_label = frappe.db.get_value("WhatsApp Account", doc.whatsapp_account, "account_name") or doc.whatsapp_account
	out.account_number = frappe.db.get_value("WhatsApp Account", doc.whatsapp_account, "phone_id")
	out.window_open = window_open(doc.last_incoming_at)
	out.can_send = can_send(doc.whatsapp_account)
	out.reference = None
	if doc.reference_doctype == "Contact" and doc.reference_name:
		out.reference = frappe._dict(
			doctype="Contact",
			name=doc.reference_name,
			title=frappe.db.get_value("Contact", doc.reference_name, "full_name") or doc.reference_name,
			status=_("Contact"),
		)
	if doc.reference_doctype in ("CRM Lead", "CRM Deal") and doc.reference_name and frappe.has_permission(
		doc.reference_doctype, "read", doc=doc.reference_name
	):
		lead = doc.reference_doctype == "CRM Lead"
		title_field, owner_field = ("lead_name", "lead_owner") if lead else ("organization", "deal_owner")
		r = frappe.db.get_value(
			doc.reference_doctype, doc.reference_name, ["name", title_field, "status", owner_field, "mobile_no"], as_dict=True
		)
		if r:
			out.reference = frappe._dict(
				doctype=doc.reference_doctype,
				name=r.name,
				title=r.get(title_field),
				status=r.status,
				owner_user=r.get(owner_field),
				mobile_no=r.mobile_no,
			)
	return out


@frappe.whitelist()
def get_thread(conversation: str):
	doc = _get(conversation)
	from crm.api.whatsapp import MESSAGE_FIELDS, enrich_messages

	if has_field():
		filters = {FIELD: doc.name}
	else:
		filters = {"whatsapp_account": doc.whatsapp_account, "from": doc.contact_number}
	messages = frappe.get_all("WhatsApp Message", filters=filters, fields=MESSAGE_FIELDS, order_by="creation asc")
	# reactions point at messages, not numbers
	ids = [m.message_id for m in messages if m.message_id]
	if ids:
		messages += frappe.get_all(
			"WhatsApp Message",
			filters={"content_type": "reaction", "reply_to_message_id": ("in", ids), "name": ("not in", [m.name for m in messages])},
			fields=MESSAGE_FIELDS,
		)
	return enrich_messages(messages, profile_name=doc.profile_name)


@frappe.whitelist()
def mark_read(conversation: str):
	doc = _get(conversation)
	if doc.unread:
		doc.db_set("unread", 0, update_modified=False)
		publish(doc.name)
	return True


@frappe.whitelist()
def set_status(conversation: str, status: str):
	if status not in ("Open", "Done"):
		frappe.throw(_("Unknown status {0}").format(status))
	doc = _get(conversation)
	doc.db_set({"status": status, "unread": 0 if status == "Done" else doc.unread}, update_modified=False)
	publish(doc.name)
	return True


def _relink(doc, reference_doctype, reference_name):
	doc.db_set(
		{
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"owner_user": _owner_of(reference_doctype, reference_name),
		},
		update_modified=False,
	)
	if has_field():
		frappe.db.sql(
			f"""update `tabWhatsApp Message` set reference_doctype=%s, reference_name=%s where `{FIELD}`=%s""",
			(reference_doctype, reference_name, doc.name),
		)
	publish(doc.name)


@frappe.whitelist()
def link_record(conversation: str, reference_doctype: str, reference_name: str):
	if reference_doctype not in ("CRM Lead", "CRM Deal"):
		frappe.throw(_("A conversation can be linked to a lead or a deal."))
	doc = _get(conversation)
	from crm.api.whatsapp import validate_access

	validate_access(reference_doctype, reference_name)
	_relink(doc, reference_doctype, reference_name)
	return True


@frappe.whitelist()
def create_lead(conversation: str):
	doc = _get(conversation)
	if doc.reference_name and doc.reference_doctype != "Contact":
		frappe.throw(_("This conversation is already linked to {0}.").format(doc.reference_name))
	lead = frappe.new_doc("CRM Lead")
	lead.first_name = doc.profile_name or ("+" + doc.contact_number)
	lead.mobile_no = "+" + doc.contact_number
	if frappe.db.exists("CRM Lead Source", "WhatsApp"):
		lead.source = "WhatsApp"
	lead.insert()
	_relink(doc, "CRM Lead", lead.name)
	return lead.name


def _new_outgoing(doc, values):
	if not can_send(doc.whatsapp_account):
		frappe.throw(_("Sending isn't switched on for this WhatsApp number yet (receive-only)."))
	message = frappe.new_doc("WhatsApp Message")
	message.update(
		{
			"type": "Outgoing",
			"to": doc.contact_number,
			"whatsapp_account": doc.whatsapp_account,
			"reference_doctype": doc.reference_doctype,
			"reference_name": doc.reference_name,
			**values,
		}
	)
	message.insert(ignore_permissions=True)
	return message.name


@frappe.whitelist()
def send(conversation: str, message: str = "", attach: str = "", content_type: str = "text", reply_to: str = ""):
	doc = _get(conversation, "write")
	if not window_open(doc.last_incoming_at):
		frappe.throw(
			_("The customer last wrote more than 24 hours ago, so WhatsApp only allows an approved template now.")
		)
	if not (message or "").strip() and not attach:
		frappe.throw(_("Type a message first."))
	values = {"message": message or attach, "attach": attach, "content_type": content_type or "text"}
	if reply_to:
		message_id = frappe.db.get_value("WhatsApp Message", reply_to, "message_id")
		if message_id:
			values.update({"is_reply": 1, "reply_to_message_id": message_id})
	return _new_outgoing(doc, values)


@frappe.whitelist()
def send_template(conversation: str, template: str):
	doc = _get(conversation, "write")
	return _new_outgoing(
		doc,
		{
			"message_type": "Template",
			"message": "Template message",
			"content_type": "text",
			"use_template": 1,
			"template": template,
		},
	)
