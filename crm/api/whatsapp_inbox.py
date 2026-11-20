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
	# a blocked sender (block()): the message is kept, silently: no unread mark, the chat stays closed
	silent = incoming and cint(conversation.get("blocked"))
	if silent:
		doc.flags.crm_blocked = True
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
	if silent:
		values["last_incoming_at"] = at
	elif incoming:
		values.update(
			{
				"last_incoming_at": at,
				"unread": cint(conversation.unread) + 1,
				"status": "Open",
			}
		)
		if doc.get("profile_name"):
			values["profile_name"] = doc.profile_name
	elif (doc.get("owner") or frappe.session.user) not in set(frappe.get_hooks("crm_assistant_users") or []):
		values["unread"] = 0  # a person answered; an AI assistant's reply leaves the chat unread for the team
	if doc.get("reference_doctype") and doc.get("reference_name"):
		values.update(
			{
				"reference_doctype": doc.reference_doctype,
				"reference_name": doc.reference_name,
				"owner_user": _owner_of(doc.reference_doctype, doc.reference_name),
			}
		)
	before = (conversation.reference_doctype, conversation.reference_name, cint(conversation.unread))
	conversation.db_set(values, update_modified=False)
	after = (conversation.reference_doctype, conversation.reference_name, cint(conversation.unread))
	if after != before:
		unread_changed(conversation, before[:2] if before[:2] != after[:2] else None)
	if has_field():
		doc.set(FIELD, conversation.name)
	return conversation.name


def unread_changed(conversation, previous_reference=None):
	"""A conversation's unread count changed (a message came in, someone read or answered it, it was marked Done or
	moved to another record). Hook `crm_whatsapp_unread_changed(conversation, previous_reference)` lets an app keep
	its own marker on the linked record; open kanban boards are told to refresh that record's card."""
	for method in frappe.get_hooks("crm_whatsapp_unread_changed"):
		frappe.db.savepoint("crm_whatsapp_unread_changed")
		try:
			frappe.get_attr(method)(conversation, previous_reference=previous_reference)
		except Exception:
			frappe.db.rollback(save_point="crm_whatsapp_unread_changed")
			frappe.log_error(frappe.get_traceback(), f"CRM WhatsApp: hook {method} failed")
	references = {(conversation.get("reference_doctype"), conversation.get("reference_name"))}
	if previous_reference:
		references.add(tuple(previous_reference))
	for doctype, name in references:
		if doctype and name:
			frappe.publish_realtime("crm_kanban_refresh", {"doctype": doctype, "name": name}, after_commit=True)


def has_block_field() -> bool:
	return frappe.get_meta("CRM WhatsApp Conversation").has_field("blocked")


def is_blocked(account, number) -> bool:
	"""This sender is blocked on this number of ours (block())."""
	number = normalize_number(number)
	if not account or not number or not has_block_field():
		return False
	return bool(
		frappe.db.exists(
			"CRM WhatsApp Conversation", {"whatsapp_account": account, "contact_number": number, "blocked": 1}
		)
	)


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
	blocked = "c.blocked" if has_block_field() else "0 as blocked"
	# over-fetch a little: unowned rows are checked against the record's assignments below
	rows = frappe.db.sql(
		f"""select c.name, c.profile_name, c.contact_number, c.whatsapp_account, c.reference_doctype,
			c.reference_name, c.owner_user, c.last_message, c.last_direction, c.last_message_at,
			c.last_incoming_at, c.unread, c.status, {blocked}
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
	out.can_draft = bool(frappe.get_hooks("crm_whatsapp_draft_reply"))
	if cint(doc.get("blocked")):
		out.blocked_by_name = frappe.db.get_value("User", doc.blocked_by, "full_name") or doc.blocked_by
	# an AI assistant app (hook crm_whatsapp_set_handler) keeps who answers this chat in the ai_* fields
	if frappe.get_hooks("crm_whatsapp_set_handler") and doc.get("ai_handler"):
		out.assistant = frappe._dict(handler=doc.ai_handler, reason=doc.get("ai_handover_reason"), stage=doc.get("ai_stage"))
		# hook crm_whatsapp_assistant_active(conversation) -> False: the assistant takes no part in this chat (e.g. a
		# number set to no automatic messages), so no "answering" badge and no hand-over buttons
		for method in frappe.get_hooks("crm_whatsapp_assistant_active"):
			if frappe.get_attr(method)(doc) is False:
				out.assistant = None
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
			out.quick_fields = quick_fields(doc.reference_doctype, doc.reference_name)
	return out


QUICK_EDIT_TYPES = ("Data", "Int", "Select", "Small Text")


def quick_fields(doctype: str, name: str, ignore_permissions: bool = False) -> list[dict]:
	"""Fields of the chat's record to show (and edit) beside the chat: hook
	`crm_whatsapp_quick_fields(doctype, name=...)` -> [{"fieldname": ..., "read_only": 0/1, "question": "..."}].
	`question` is a ready message that asks the customer for that detail (the inbox's "Ask" button). Fields the
	doctype doesn't have are skipped; a field is read-only when the hook, the field itself or the user's permission
	says so, or its type isn't a simple one."""
	specs = []
	for method in frappe.get_hooks("crm_whatsapp_quick_fields"):
		try:
			specs.extend(frappe.get_attr(method)(doctype, name=name) or [])
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"CRM WhatsApp: hook {method} failed")
	meta = frappe.get_meta(doctype)
	fields = []
	for spec in specs:
		df = meta.get_field(spec.get("fieldname"))
		if df and df.fieldname not in [f[0].fieldname for f in fields]:
			fields.append((df, spec))
	if not fields:
		return []
	can_write = ignore_permissions or frappe.has_permission(doctype, "write", doc=name)
	values = frappe.db.get_value(doctype, name, [df.fieldname for df, _spec in fields], as_dict=True) or {}
	return [
		{
			"fieldname": df.fieldname,
			"label": _(df.label),
			"fieldtype": df.fieldtype,
			"options": [o for o in (df.options or "").split("\n")] if df.fieldtype == "Select" else None,
			"value": values.get(df.fieldname),
			"question": spec.get("question") or "",
			"read_only": int(
				bool(spec.get("read_only")) or bool(df.read_only) or not can_write or df.fieldtype not in QUICK_EDIT_TYPES
			),
		}
		for df, spec in fields
	]


ASK_TTL = 72 * 3600


def _ask_key(conversation: str) -> str:
	return f"crm_whatsapp_asked::{conversation}"


def pending_asks(conversation: str) -> list[str]:
	"""Quick fields a rep asked the customer about and that aren't filled yet (kept 72 hours)."""
	return list(frappe.cache.get_value(_ask_key(conversation)) or [])


def clear_asks(conversation: str, fieldnames: list[str] | None = None):
	left = [f for f in pending_asks(conversation) if fieldnames is not None and f not in fieldnames]
	if left:
		frappe.cache.set_value(_ask_key(conversation), left, expires_in_sec=ASK_TTL)
	else:
		frappe.cache.delete_value(_ask_key(conversation))


@frappe.whitelist(methods=["POST"])
def ask_quick_field(conversation: str, fieldname: str):
	"""The rep pressed "Ask" on a quick field: returns the question for the message box and remembers that it was
	asked, so an assistant app can read the customer's answer (it calls pending_asks and fill_quick_fields)."""
	doc = _get(conversation, "write")
	field = next(
		(f for f in quick_fields(doc.reference_doctype, doc.reference_name) if f["fieldname"] == fieldname), None
	)
	if not field or field["read_only"] or not field["question"]:
		frappe.throw(_("There is no question for this field."))
	asked = [f for f in pending_asks(conversation) if f != fieldname] + [fieldname]
	frappe.cache.set_value(_ask_key(conversation), asked, expires_in_sec=ASK_TTL)
	return {"question": field["question"]}


def fill_quick_fields(conversation: str, values: dict, by: str | None = None) -> dict:
	"""For an assistant app: put the customer's answers into the record's quick fields. Only listed, editable fields
	that are still blank; a value a person typed is never replaced. Leaves a comment naming what was filled."""
	doc = frappe.get_doc("CRM WhatsApp Conversation", conversation)
	if doc.reference_doctype not in ("CRM Lead", "CRM Deal") or not doc.reference_name:
		return {}
	filled, labels = {}, []
	for f in quick_fields(doc.reference_doctype, doc.reference_name, ignore_permissions=True):
		value = values.get(f["fieldname"])
		if f["read_only"] or f["value"] not in (None, "", 0) or value in (None, ""):
			continue
		if f["fieldtype"] == "Int":
			value = cint(value)
			if not value:
				continue
		else:
			value = strip_html(str(value)).strip()[:140]
			if not value or (f["fieldtype"] == "Select" and value not in (f["options"] or [])):
				continue
		filled[f["fieldname"]] = value
		labels.append(f"{f['label']}: {value}")
	if filled:
		frappe.db.set_value(doc.reference_doctype, doc.reference_name, filled, update_modified=False)
		frappe.get_doc(doc.reference_doctype, doc.reference_name).add_comment(
			"Info", text=frappe.utils.escape_html(f"{by or 'Assistant'} filled from the WhatsApp chat: " + "; ".join(labels))
		)
		clear_asks(conversation, list(filled))
		publish(conversation)
	return filled


@frappe.whitelist(methods=["POST"])
def set_quick_field(conversation: str, fieldname: str, value: str | int | None = None):
	"""Save one of the quick fields on the chat's lead or deal. Only fields the hook lists as editable; the record is
	saved the normal way, so its own validation and permissions apply."""
	doc = _get(conversation, "write")
	if doc.reference_doctype not in ("CRM Lead", "CRM Deal") or not doc.reference_name:
		frappe.throw(_("This conversation isn't linked to a lead or deal."))
	field = next(
		(f for f in quick_fields(doc.reference_doctype, doc.reference_name) if f["fieldname"] == fieldname), None
	)
	if not field or field["read_only"]:
		frappe.throw(_("This field can't be changed here."), frappe.PermissionError)
	if field["fieldtype"] == "Int":
		value = cint(value)
	else:
		value = strip_html(str(value or "")).strip()
		if field["fieldtype"] == "Data":
			value = value[:140]
		if field["fieldtype"] == "Select" and value not in (field["options"] or []):
			frappe.throw(_("{0} is not one of the choices.").format(value))
	record = frappe.get_doc(doc.reference_doctype, doc.reference_name)
	record.check_permission("write")
	record.set(fieldname, value)
	record.save()
	clear_asks(conversation, [fieldname])
	return {"value": record.get(fieldname)}


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
	return _with_ads(enrich_messages(messages, profile_name=doc.profile_name))


def _with_ads(messages):
	"""A chat started from an ad: the first message carries Meta's `referral` (frappe_whatsapp keeps it). The inbox
	shows the ad and the greeting Meta showed the customer above that message."""
	names = [m.get("name") for m in messages if m.get("type") == "Incoming"]
	if not names or not frappe.get_meta("WhatsApp Message").has_field("referral"):
		return messages
	referrals = dict(
		frappe.get_all(
			"WhatsApp Message",
			filters={"name": ("in", names), "referral": ("is", "set")},
			fields=["name", "referral"],
			as_list=True,
		)
	)
	for m in messages:
		raw = referrals.get(m.get("name"))
		if not raw:
			continue
		try:
			ref = frappe.parse_json(raw) if isinstance(raw, str) else raw
		except ValueError:
			continue
		if not isinstance(ref, dict) or not ref:
			continue
		welcome = ref.get("welcome_message")
		m["ad"] = {
			"kind": "post" if ref.get("source_type") == "post" else "ad",
			"headline": ref.get("headline") or "",
			"body": ref.get("body") or "",
			"url": ref.get("source_url") or "",
			"greeting": (welcome.get("text") if isinstance(welcome, dict) else "") or "",
		}
	return messages


@frappe.whitelist()
def mark_read(conversation: str):
	doc = _get(conversation)
	if doc.unread:
		doc.db_set("unread", 0, update_modified=False)
		unread_changed(doc)
		publish(doc.name)
	elif _marker_left(doc.reference_doctype, doc.reference_name):
		unread_changed(doc)  # the chat is read but its record still shows unread: put the marker right
	return True


def _marker_left(doctype, name) -> bool:
	"""The record's kanban marker (hook crm_kanban_marker) still counts unread messages."""
	if not doctype or not name:
		return False
	from crm.api.doc import get_kanban_marker

	field = (get_kanban_marker(doctype) or {}).get("count_field")
	return bool(field and cint(frappe.db.get_value(doctype, name, field)))


@frappe.whitelist()
def mark_record_read(doctype: str, name: str):
	"""Someone opened the WhatsApp tab of a lead, deal or contact: its conversations are read, as in the inbox."""
	if not frappe.has_permission(doctype, "read", doc=name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("DocType", "CRM WhatsApp Conversation"):
		return False
	names = frappe.get_all(
		"CRM WhatsApp Conversation",
		filters={"reference_doctype": doctype, "reference_name": name, "unread": (">", 0)},
		pluck="name",
	)
	for conversation in names:
		doc = frappe.get_doc("CRM WhatsApp Conversation", conversation)
		doc.db_set("unread", 0, update_modified=False)
		unread_changed(doc)
		publish(doc.name)
	if not names and _marker_left(doctype, name):
		# every chat is read but the record still shows unread: put the marker right
		rest = frappe.get_all(
			"CRM WhatsApp Conversation", filters={"reference_doctype": doctype, "reference_name": name}, pluck="name", limit=1
		)
		if rest:
			unread_changed(frappe.get_doc("CRM WhatsApp Conversation", rest[0]))
	return bool(names)


@frappe.whitelist(methods=["POST"])
def set_handler(conversation: str, handler: str):
	"""Take over from / hand back to the AI assistant, or pause it (hook crm_whatsapp_set_handler)."""
	methods = frappe.get_hooks("crm_whatsapp_set_handler")
	if not methods:
		frappe.throw(_("No AI assistant is set up for WhatsApp."))
	_get(conversation, "write")
	out = frappe.get_attr(methods[-1])(conversation, handler)
	publish(conversation)
	return out


def _block_hooks(doc, blocked: bool):
	"""Hook `crm_whatsapp_blocked(conversation, blocked=True/False)`: an app's own follow-up (e.g. mark the lead as spam)."""
	for method in frappe.get_hooks("crm_whatsapp_blocked"):
		frappe.db.savepoint("crm_whatsapp_blocked")
		try:
			frappe.get_attr(method)(doc, blocked=blocked)
		except Exception:
			frappe.db.rollback(save_point="crm_whatsapp_blocked")
			frappe.log_error(frappe.get_traceback(), f"CRM WhatsApp: hook {method} failed")


def _block_on_whatsapp(doc, unblock: bool = False) -> dict:
	if not can_send(doc.whatsapp_account):
		return {"ok": False, "error": _("This WhatsApp number has no access token (receive-only).")}
	try:
		from frappe_whatsapp.utils import block_number
	except ImportError:
		return {"ok": False, "error": _("The WhatsApp app on this site can't block numbers yet.")}
	return block_number(doc.whatsapp_account, doc.contact_number, unblock=unblock)


@frappe.whitelist(methods=["POST"])
def block(conversation: str):
	"""Block the sender of this chat (abuse, spam): WhatsApp stops delivering their messages to this number of ours,
	the chat is closed, and apps get `crm_whatsapp_blocked`. WhatsApp only blocks someone who wrote in the last 24
	hours; when it refuses, the block still holds in the CRM: later messages are kept silently (no unread mark, no
	lead handling, no notification). Same access as replying in the chat."""
	doc = _get(conversation, "write")
	if not has_block_field():
		frappe.throw(_("Blocking isn't set up on this site yet."))
	if cint(doc.blocked):
		return {"on_whatsapp": bool(cint(doc.blocked_on_whatsapp)), "error": doc.block_note}
	result = _block_on_whatsapp(doc)
	had_unread = cint(doc.unread)
	doc.db_set(
		{
			"blocked": 1,
			"blocked_on_whatsapp": 1 if result.get("ok") else 0,
			"blocked_by": frappe.session.user,
			"blocked_at": now_datetime(),
			"block_note": None if result.get("ok") else (result.get("error") or "")[:300],
			"status": "Done",
			"unread": 0,
		},
		update_modified=False,
	)
	if had_unread:
		unread_changed(doc)
	_block_hooks(doc, True)
	publish(doc.name)
	return {"on_whatsapp": bool(result.get("ok")), "error": result.get("error")}


@frappe.whitelist(methods=["POST"])
def unblock(conversation: str):
	doc = _get(conversation, "write")
	if not cint(doc.get("blocked")):
		return True
	if cint(doc.blocked_on_whatsapp):
		result = _block_on_whatsapp(doc, unblock=True)
		if not result.get("ok"):
			frappe.throw(_("WhatsApp did not unblock the number: {0}").format(result.get("error") or ""))
	doc.db_set(
		{"blocked": 0, "blocked_on_whatsapp": 0, "blocked_by": None, "blocked_at": None, "block_note": None, "status": "Open"},
		update_modified=False,
	)
	_block_hooks(doc, False)
	publish(doc.name)
	return True


@frappe.whitelist()
def set_status(conversation: str, status: str):
	if status not in ("Open", "Done"):
		frappe.throw(_("Unknown status {0}").format(status))
	doc = _get(conversation)
	had_unread = cint(doc.unread)
	doc.db_set({"status": status, "unread": 0 if status == "Done" else doc.unread}, update_modified=False)
	if had_unread != cint(doc.unread):
		unread_changed(doc)
	publish(doc.name)
	return True


def _relink(doc, reference_doctype, reference_name):
	previous = (doc.reference_doctype, doc.reference_name)
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
	if previous != (reference_doctype, reference_name):
		unread_changed(doc, previous)
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


@frappe.whitelist(methods=["POST"])
def draft_reply(conversation: str, language: str | None = None, instruction: str | None = None):
	"""A draft for the composer from the app that registered hook
	`crm_whatsapp_draft_reply(conversation, language, instruction)` (e.g. an AI assistant). `instruction` is what the
	rep typed in the reply box: a rough draft to rewrite, or a note on what to say. `language` is the language the rep
	picked (none: the assistant decides). It only returns text; the rep edits and sends it."""
	_get(conversation, "write")
	methods = frappe.get_hooks("crm_whatsapp_draft_reply")
	if not methods:
		frappe.throw(_("No draft assistant is installed."))
	kwargs = {"language": (language or "").strip()[:40] or None}
	if (instruction or "").strip():
		kwargs["instruction"] = instruction.strip()[:4000]
	out = frappe.get_attr(methods[-1])(conversation, **kwargs)
	return {"reply": (out or {}).get("reply") or ""}


def _new_outgoing(doc, values):
	if not can_send(doc.whatsapp_account):
		frappe.throw(_("Sending isn't switched on for this WhatsApp number yet (receive-only)."))
	if cint(doc.get("blocked")):
		frappe.throw(_("This number is blocked. Unblock it before writing to it."))
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
def send_template(conversation: str, template: str, values: str | dict | None = None, language: str | None = None):
	doc = _get(conversation, "write")
	from crm.api.whatsapp import template_hook

	hook = template_hook("crm_whatsapp_send_template")
	if hook and values is not None and doc.reference_doctype and doc.reference_name:
		if not can_send(doc.whatsapp_account):
			frappe.throw(_("Sending isn't switched on for this WhatsApp number yet (receive-only)."))
		values = frappe.parse_json(values) if isinstance(values, str) else values
		route = {"to": doc.contact_number, "whatsapp_account": doc.whatsapp_account}
		return hook(doc.reference_doctype, doc.reference_name, template, values, language, route)
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
