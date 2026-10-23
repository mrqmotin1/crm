"""Merge a lead-form submission into the lead that already holds its phone number.

Off unless the Lead Sync Source has "Merge into existing lead" switched on. Then a submission whose phone number belongs to
an open lead updates that lead instead of failing:

- only blank fields are filled (from the form's own question → field mapping), never name, phone, email, owner or status
  fields; source and the Meta lead/form IDs only when blank;
- a note "Meta form submission <id>" lists every answer;
- the status is judged as it was when the person submitted the form (from the lead's status change log): a lead that was
  Lost or On Hold comes back to the first Open status; an active lead older than "returning after" days keeps its status
  and its owner gets a task; a status that staff changed after the submission is left alone;
- the same submission is never applied twice (Meta ID on the lead, or its note exists).

Sites can supply their own phone lookup (hook `crm_lead_sync_find_lead`) and react to a merge (hook
`crm_lead_sync_merged`).
"""

import re
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, escape_html, get_datetime, now_datetime
from frappe.utils.data import convert_utc_to_system_timezone

PROTECTED = {
	"first_name",
	"last_name",
	"lead_name",
	"mobile_no",
	"phone",
	"email",
	"lead_owner",
	"status",
	"converted",
	"naming_series",
}
DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
NOTE_TITLE = "Meta form submission {0}"
LOCK_SECONDS = 120
# Meta gives whole seconds and its clock is not ours: a status change within a minute of the submission is not "later"
CLOCK_GRACE_SECONDS = 60


# ---------------------------------------------------------------- phone numbers


def normalise_phone(value) -> str:
	"""Digits only, Bangla/Arabic digits folded, a leading 00 dropped; Bangladesh numbers in any form (01…, 1…, 8801…,
	+8801…) become 8801…. Other countries keep their own country code."""
	digits = re.sub(r"\D", "", str(value or "").translate(DIGITS))
	if digits.startswith("00"):
		digits = digits[2:]
	if len(digits) == 11 and digits.startswith("01"):
		return "88" + digits
	if len(digits) == 10 and digits.startswith("1"):
		return "880" + digits
	return digits


def find_existing_lead(phone) -> dict:
	"""{"lead": name} for an open lead with the same full number, {"conflict": name} when only the last 10 digits match
	(another country code), or {}."""
	number = normalise_phone(phone)
	if len(number) < 8:
		return {}
	candidates = []
	for hook in frappe.get_hooks("crm_lead_sync_find_lead"):
		found = frappe.get_attr(hook)(phone)
		candidates += [found] if isinstance(found, str) else list(found or [])
	if not frappe.get_hooks("crm_lead_sync_find_lead"):
		candidates = frappe.db.sql_list(
			"""select name from `tabCRM Lead`
			where converted = 0 and regexp_replace(ifnull(mobile_no, ''), '[^0-9]', '') like %s
			order by modified desc limit 20""",
			f"%{number[-10:]}",
		)
	conflict = None
	for name in dict.fromkeys(c for c in candidates if c):
		row = frappe.db.get_value("CRM Lead", name, ["mobile_no", "converted"], as_dict=True)
		if not row or cint(row.converted):
			continue
		if normalise_phone(row.mobile_no) == number:
			return {"lead": name}
		if normalise_phone(row.mobile_no)[-10:] == number[-10:]:
			conflict = conflict or name
	return {"conflict": conflict} if conflict else {}


# ---------------------------------------------------------------- submissions


def answers(submission: dict) -> dict:
	"""Meta's field_data as {question key: first value} (fields Meta sends empty are left out)."""
	return {f["name"]: f["values"][0] for f in submission.get("field_data") or [] if f.get("values")}


def _utc(submission: dict):
	"""Meta's created_time as an aware UTC datetime, or None."""
	value = submission.get("created_time")
	if not value:
		return None
	try:
		return datetime.fromisoformat(value.replace("+0000", "+00:00"))
	except ValueError:
		return None


def submitted_at(submission: dict):
	"""When the person sent the form, in the site's time zone (lead dates, notes); now if unknown."""
	utc = _utc(submission)
	if not utc:
		return now_datetime()
	return get_datetime(convert_utc_to_system_timezone(utc.replace(tzinfo=None))).replace(tzinfo=None)


def submitted_server_time(submission: dict):
	"""The same moment on the server's clock: the status change log is stamped with datetime.now() (the process's local
	time, UTC in our containers), not the site's time zone."""
	utc = _utc(submission)
	return datetime.fromtimestamp(utc.timestamp()) if utc else datetime.now()


def phone_of(submission: dict, mapping: dict) -> str | None:
	data = answers(submission)
	for key, field in mapping.items():
		if field == "mobile_no" and data.get(key):
			return data[key]
	return data.get("phone_number")


def already_merged(meta_id: str) -> str | None:
	"""The lead this submission was already applied to (its Meta ID, or its note)."""
	return frappe.db.get_value("CRM Lead", {"facebook_lead_id": meta_id}, "name") or frappe.db.get_value(
		"FCRM Note",
		{"title": NOTE_TITLE.format(meta_id), "reference_doctype": "CRM Lead"},
		"reference_docname",
	)


# ---------------------------------------------------------------- statuses


def status_type(status: str | None) -> str | None:
	return frappe.db.get_value("CRM Lead Status", status, "type") if status else None


def first_open_status() -> str | None:
	return frappe.db.get_value("CRM Lead Status", {"type": "Open"}, "name", order_by="position asc")


def status_changed_after(lead, when) -> bool:
	"""Whether the lead's status changed after `when` (server clock, like the status change log). If it didn't, the
	status the person saw when submitting is the lead's current status (old log rows may carry renamed statuses)."""
	when = when + timedelta(seconds=CLOCK_GRACE_SECONDS)
	return any(r.to_date and get_datetime(r.to_date) > when for r in lead.get("status_change_log") or [])


# ---------------------------------------------------------------- the merge


def plan(lead_name: str, submission: dict, form_id: str, returning_after_days: int = 7) -> dict:
	"""What a merge would do, without writing anything."""
	lead = frappe.get_doc("CRM Lead", lead_name)
	meta = frappe.get_meta("CRM Lead")
	mapping = form_mapping(form_id)
	data = answers(submission)
	when = submitted_at(submission)

	fill, skipped = {}, {}
	for key, value in data.items():
		field = mapping.get(key)
		if not field or field in PROTECTED or not meta.has_field(field):
			continue
		df = meta.get_field(field)
		if lead.get(field) not in (None, ""):
			continue
		if df.fieldtype == "Select" and value not in (df.options or "").split("\n"):
			skipped[field] = value
			continue
		if df.fieldtype in ("Int", "Float", "Currency") and not str(value).replace(".", "", 1).isdigit():
			skipped[field] = value
			continue
		fill[field] = (
			value[: df.length or 140] if df.fieldtype == "Data" and isinstance(value, str) else value
		)
	if not lead.source and frappe.db.exists("CRM Lead Source", "Facebook"):
		fill["source"] = "Facebook"
	if not lead.facebook_lead_id:
		fill["facebook_lead_id"] = submission["id"]
	if not lead.facebook_form_id:
		fill["facebook_form_id"] = form_id

	changed_after = status_changed_after(lead, submitted_server_time(submission))
	status_then = None if changed_after else lead.status
	kind = status_type(lead.status)
	new_status = first_open_status()
	old_lead = get_datetime(lead.creation) < add_days(when, -cint(returning_after_days or 7))
	if changed_after:
		action = "kept"  # staff decided after the submission
	elif kind in ("Lost", "On Hold"):
		action = "reopened"
	elif old_lead and lead.status == new_status:
		action = "restarted"  # still New: the follow-up clock starts again
	elif old_lead and kind in ("Open", "Ongoing", "Won"):
		action = "alerted"  # being worked on: keep the status, tell the owner
	else:
		action = "updated"
	return {
		"lead": lead.name,
		"meta_id": submission["id"],
		"submitted_at": str(when),
		"status_then": status_then,
		"status_now": lead.status,
		"action": action,
		"new_status": new_status if action == "reopened" else lead.status,
		"fill": fill,
		"not_filled": skipped,
		"kept_meta_id": lead.facebook_lead_id
		if lead.facebook_lead_id and lead.facebook_lead_id != submission["id"]
		else None,
	}


def apply(lead_name: str, submission: dict, form_id: str, returning_after_days: int = 7) -> dict:
	"""Merge the submission into the lead (idempotent). Returns the plan with "done": True, or "skipped"."""
	meta_id = submission["id"]
	key = frappe.cache.make_key(f"crm_lead_sync_merge:{meta_id}")
	if not frappe.cache.set(key, 1, nx=True, ex=LOCK_SECONDS):
		return {
			"lead": lead_name,
			"meta_id": meta_id,
			"skipped": "another merge of this submission is running",
		}
	try:
		done = already_merged(meta_id)
		if done:
			return {"lead": done, "meta_id": meta_id, "skipped": "already merged"}
		p = plan(lead_name, submission, form_id, returning_after_days)
		frappe.db.savepoint("crm_lead_sync_merge")
		try:
			_write(p, submission, form_id)
		except Exception:
			frappe.db.rollback(save_point="crm_lead_sync_merge")
			raise
		for hook in frappe.get_hooks("crm_lead_sync_merged"):
			try:
				frappe.get_attr(hook)(p["lead"], p)
			except Exception:
				frappe.log_error(title=f"crm_lead_sync_merged hook failed: {hook}")
		p["done"] = True
		return p
	finally:
		frappe.cache.delete(key)


def _write(p: dict, submission: dict, form_id: str):
	lead = frappe.get_doc("CRM Lead", p["lead"])
	before = {
		"status": lead.status,
		"lost_reason": lead.get("lost_reason"),
		"lost_notes": lead.get("lost_notes"),
	}
	for field, value in p["fill"].items():
		lead.set(field, value)
	if p["action"] == "reopened" and p["new_status"]:
		lead.status = p["new_status"]
		lead.lost_reason = None
		lead.lost_notes = None
	lead.flags.from_lead_sync = True
	lead.flags.ignore_permissions = True
	lead.save()
	frappe.get_doc(
		{
			"doctype": "FCRM Note",
			"title": NOTE_TITLE.format(p["meta_id"]),
			"content": note_html(p, submission, form_id, before),
			"reference_doctype": "CRM Lead",
			"reference_docname": lead.name,
		}
	).insert(ignore_permissions=True)
	if p["action"] == "alerted" and lead.lead_owner:
		frappe.get_doc(
			{
				"doctype": "CRM Task",
				"title": _("Came back via Meta form"),
				"description": _('{0} sent the lead form again on {1}. See the note "{2}".').format(
					escape_html(lead.lead_name or lead.name),
					p["submitted_at"][:16],
					NOTE_TITLE.format(p["meta_id"]),
				),
				"status": "Todo",
				"priority": "High",
				"due_date": now_datetime(),
				"assigned_to": lead.lead_owner,
				"reference_doctype": "CRM Lead",
				"reference_docname": lead.name,
			}
		).insert(ignore_permissions=True)


def note_html(p: dict, submission: dict, form_id: str, before: dict) -> str:
	labels = {
		q.key: q.label
		for q in frappe.get_all(
			"Facebook Lead Form Question", filters={"parent": form_id}, fields=["key", "label"]
		)
	}
	form_name = frappe.db.get_value("Facebook Lead Form", form_id, "form_name") or form_id
	rows = "".join(
		f"<li>{escape_html(labels.get(k) or k.replace('_', ' '))}: <b>{escape_html(str(v))}</b></li>"
		for k, v in answers(submission).items()
	)
	lines = [
		f"<p>{escape_html(form_name)} · {escape_html(p['submitted_at'][:16])} · Meta ID {escape_html(p['meta_id'])}</p>",
		f"<ul>{rows}</ul>",
	]
	meta = frappe.get_meta("CRM Lead")

	def labels_of(fields):
		return escape_html(", ".join(sorted(_(meta.get_label(f)) for f in fields)))

	if p["fill"]:
		lines.append(f"<p>Filled empty fields: {labels_of(p['fill'])}</p>")
	if p.get("not_filled"):
		lines.append(f"<p>Not filled (value not allowed in the field): {labels_of(p['not_filled'])}</p>")
	if p.get("kept_meta_id"):
		lines.append(
			f"<p>The lead keeps its earlier Meta ID {escape_html(p['kept_meta_id'])}; this submission is {escape_html(p['meta_id'])}.</p>"
		)
	status_line = {
		"reopened": f"Came back: status {escape_html(before['status'] or '')} → {escape_html(p['new_status'] or '')}."
		+ (f" Lost reason was: {escape_html(before['lost_reason'])}." if before.get("lost_reason") else "")
		+ (f" Lost notes were: {escape_html(before['lost_notes'])}." if before.get("lost_notes") else ""),
		"alerted": "Came back while being worked on: status kept, a task was created for the owner.",
		"restarted": "Came back: still New, the follow-up clock starts again.",
		"kept": f"Status kept ({escape_html(before['status'] or '')}): it was changed after this submission.",
		"updated": "",
	}[p["action"]]
	if status_line:
		lines.append(f"<p>{status_line}</p>")
	return "".join(lines)


def form_mapping(form_id: str) -> dict:
	return {
		q.key: q.mapped_to_crm_field
		for q in frappe.get_all(
			"Facebook Lead Form Question", filters={"parent": form_id}, fields=["key", "mapped_to_crm_field"]
		)
		if q.mapped_to_crm_field
	}


# ---------------------------------------------------------------- retry the failure logs of a source


@frappe.whitelist(methods=["POST"])
def retry_failed(source: str, dry_run: int = 1) -> dict:
	"""Retry every unsynced failure log of a source, oldest first, once per Meta lead. Repeats of a submission that is
	in the CRM become Synced. dry_run (default) only reports what would happen."""
	frappe.has_permission("Lead Sync Source", "write", source, throw=True)
	from crm.lead_syncing.doctype.lead_sync_source.facebook import FacebookSyncSource

	src = frappe.get_doc("Lead Sync Source", source)
	if src.type != "Facebook":
		frappe.throw(_("Not implemented yet!"))
	dry_run = cint(dry_run)
	logs = frappe.get_all(
		"Failed Lead Sync Log",
		filters={"source": source, "type": ("!=", "Synced")},
		fields=["name", "lead_data"],
		order_by="creation asc",
	)
	sync = FacebookSyncSource(
		src.get_password("access_token", raise_exception=False), src.facebook_lead_form, source_name=source
	)
	results, seen = [], {}
	summary = {
		"logs": len(logs),
		"submissions": 0,
		"merged": 0,
		"inserted": 0,
		"already_in_crm": 0,
		"conflicts": 0,
		"failed": 0,
		"repeats": 0,
	}
	for log in logs:
		submission = frappe.parse_json(log.lead_data) or {}
		meta_id = submission.get("id")
		if not meta_id:
			continue
		if meta_id in seen:
			summary["repeats"] += 1
			if not dry_run and seen[meta_id] in ("merged", "inserted", "already_in_crm"):
				frappe.db.set_value("Failed Lead Sync Log", log.name, "type", "Synced", update_modified=False)
			continue
		summary["submissions"] += 1
		outcome = _retry_one(sync, src, log, submission, dry_run)
		seen[meta_id] = outcome["result"]
		summary[outcome["result"]] = summary.get(outcome["result"], 0) + 1
		results.append(outcome)
		if not dry_run:
			frappe.db.commit()
	return {"dry_run": bool(dry_run), "summary": summary, "results": results}


def _retry_one(sync, src, log, submission: dict, dry_run: int) -> dict:
	meta_id = submission["id"]
	out = {"log": log.name, "meta_id": meta_id}
	done = already_merged(meta_id)
	if done:
		if not dry_run:
			frappe.db.set_value("Failed Lead Sync Log", log.name, "type", "Synced", update_modified=False)
		return {**out, "result": "already_in_crm", "lead": done}
	mapping = sync.get_form_questions_mapping()
	found = find_existing_lead(phone_of(submission, mapping)) if src.get("merge_duplicates") else {}
	if found.get("conflict"):
		return {
			**out,
			"result": "conflicts",
			"lead": found["conflict"],
			"note": "same last 10 digits, different country code",
		}
	if found.get("lead"):
		if dry_run:
			return {
				**out,
				"result": "merged",
				**plan(
					found["lead"], submission, src.facebook_lead_form, src.get("returning_after_days") or 7
				),
			}
		try:
			res = apply(
				found["lead"], submission, src.facebook_lead_form, src.get("returning_after_days") or 7
			)
			frappe.db.set_value("Failed Lead Sync Log", log.name, "type", "Synced", update_modified=False)
			frappe.get_doc("Failed Lead Sync Log", log.name).add_comment(
				"Comment", text=f"Merged into {res['lead']}"
			)
			return {**out, "result": "merged", **res}
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title=f"Lead sync merge failed: {meta_id}")
			return {**out, "result": "failed", "error": str(e)[:300]}
	if dry_run:
		return {
			**out,
			"result": "inserted",
			"note": "no lead with this number: would be created as a new lead",
		}
	try:
		lead = sync.sync_single_lead(submission, raise_exception=True)
		frappe.db.set_value("Failed Lead Sync Log", log.name, "type", "Synced", update_modified=False)
		return {**out, "result": "inserted", "lead": getattr(lead, "name", lead)}
	except Exception as e:
		frappe.db.rollback()
		return {**out, "result": "failed", "error": str(e)[:300]}
