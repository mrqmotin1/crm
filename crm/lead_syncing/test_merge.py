import random
from datetime import timedelta

import frappe
try:  # v16: test records load lazily
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # v15
	from frappe.tests.utils import FrappeTestCase as TestCase
from frappe.utils import add_days, now_datetime

from crm.lead_syncing import merge

FORM = "test-merge-form"


def number() -> str:
	return "017" + "".join(random.choice("0123456789") for _ in range(8))


def status_of(kind: str) -> str:
	return frappe.db.get_value("CRM Lead Status", {"type": kind}, "name", order_by="position asc")


def submission(meta_id: str, phone: str, created=None, **answers) -> dict:
	created = created or now_datetime()
	utc = created - timedelta(hours=6)  # tests run with the site's zone; only the order of events matters
	fields = [{"name": "full_name", "values": ["Meta Person"]}, {"name": "phone_number", "values": [phone]}]
	fields += [{"name": k, "values": [v]} for k, v in answers.items()]
	fields.append({"name": "email", "values": ["meta.person@example.com"]})
	return {"id": meta_id, "created_time": utc.strftime("%Y-%m-%dT%H:%M:%S+0000"), "field_data": fields}


class TestLeadSyncMerge(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Facebook Lead Form", FORM):
			frappe.db.sql(
				"insert into `tabFacebook Lead Form` (name, form_name, creation, modified, owner, modified_by) values (%s, %s, now(), now(), 'Administrator', 'Administrator')",
				(FORM, "Test merge form"),
			)
		frappe.db.delete("Facebook Lead Form Question", {"parent": FORM})
		for i, (key, field, label) in enumerate(
			[
				("full_name", "first_name", "Full name"),
				("phone_number", "mobile_no", "Phone"),
				("job", "job_title", "Your role"),
				("website", "website", "Website"),
			]
		):
			frappe.get_doc(
				{
					"doctype": "Facebook Lead Form Question",
					"parent": FORM,
					"parenttype": "Facebook Lead Form",
					"parentfield": "questions",
					"idx": i + 1,
					"key": key,
					"label": label,
					"mapped_to_crm_field": field,
				}
			).db_insert()
		cls.converted = frappe.db.get_value("CRM Lead", {"converted": 1}, "name")

	def lead(self, phone, status=None, created=None, **values):
		doc = frappe.get_doc(
			{"doctype": "CRM Lead", "first_name": "Existing", "mobile_no": phone, **values}
		).insert(ignore_permissions=True)
		if status and status != doc.status:
			kind = frappe.db.get_value("CRM Lead Status", status, "type")
			doc.status = status
			if kind == "Lost":
				doc.lost_reason = frappe.db.get_value("CRM Lost Reason", {}, "name")
				doc.lost_notes = "test"
			doc.flags.from_lead_sync = True
			doc.save(ignore_permissions=True)
		if created:
			frappe.db.set_value("CRM Lead", doc.name, "creation", created, update_modified=False)
			for row in frappe.get_all("CRM Status Change Log", filters={"parent": doc.name}, pluck="name"):
				frappe.db.set_value("CRM Status Change Log", row, "from_date", created, update_modified=False)
		return frappe.get_doc("CRM Lead", doc.name)

	def test_normalise(self):
		for value in (
			"01712345678",
			"+8801712345678",
			"8801712345678",
			"1712345678",
			"০১৭১২৩৪৫৬৭৮",
			"+880 1712-345678",
			"008801712345678",
		):
			self.assertEqual(merge.normalise_phone(value), "8801712345678", value)
		self.assertEqual(merge.normalise_phone("+971 50 123 4567"), "971501234567")

	def test_find_and_conflict(self):
		phone = number()
		lead = self.lead(phone)
		self.assertEqual(merge.find_existing_lead("+88" + phone), {"lead": lead.name})
		self.assertEqual(merge.find_existing_lead("+971" + phone[1:]), {"conflict": lead.name})
		self.assertEqual(merge.find_existing_lead(number()), {})

	def test_fill_blanks_only_and_note(self):
		phone = number()
		lead = self.lead(phone, website="https://kept.example.com")
		res = merge.apply(
			lead.name, submission("9001", phone, job="Owner", website="https://new.example.com"), FORM
		)
		lead.reload()
		self.assertTrue(res["done"])
		self.assertEqual(lead.job_title, "Owner")
		self.assertEqual(lead.website, "https://kept.example.com")
		self.assertEqual(lead.first_name, "Existing")
		self.assertFalse(lead.email)
		self.assertEqual((lead.facebook_lead_id, lead.facebook_form_id), ("9001", FORM))
		note = frappe.db.get_value(
			"FCRM Note",
			{"title": "Meta form submission 9001"},
			["reference_docname", "content"],
			as_dict=True,
		)
		self.assertEqual(note.reference_docname, lead.name)
		self.assertIn("Your role", note.content)
		self.assertIn("meta.person@example.com", note.content)

	def test_idempotent(self):
		phone = number()
		lead = self.lead(phone)
		merge.apply(lead.name, submission("9002", phone), FORM)
		again = merge.apply(lead.name, submission("9002", phone), FORM)
		self.assertEqual(again["skipped"], "already merged")
		self.assertEqual(frappe.db.count("FCRM Note", {"title": "Meta form submission 9002"}), 1)

	def test_keeps_older_meta_id(self):
		phone = number()
		lead = self.lead(phone, facebook_lead_id="8000")
		res = merge.apply(lead.name, submission("9003", phone), FORM)
		self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "facebook_lead_id"), "8000")
		self.assertEqual(res["kept_meta_id"], "8000")
		self.assertEqual(merge.already_merged("9003"), lead.name)

	def test_lost_comes_back(self):
		phone = number()
		lead = self.lead(phone, status=status_of("Lost"), created=add_days(now_datetime(), -20))
		res = merge.apply(lead.name, submission("9004", phone), FORM)
		lead.reload()
		self.assertEqual(res["action"], "reopened")
		self.assertEqual(lead.status, merge.first_open_status())
		self.assertFalse(lead.lost_reason)
		self.assertIn(
			"Came back", frappe.db.get_value("FCRM Note", {"title": "Meta form submission 9004"}, "content")
		)

	def test_on_hold_comes_back(self):
		on_hold = status_of("On Hold")
		if not on_hold:
			self.skipTest("no On Hold status")
		phone = number()
		lead = self.lead(phone, status=on_hold)
		self.assertEqual(merge.apply(lead.name, submission("9005", phone), FORM)["action"], "reopened")

	def test_active_old_lead_keeps_status_and_gets_task(self):
		ongoing = status_of("Ongoing")
		phone = number()
		lead = self.lead(
			phone, status=ongoing, created=add_days(now_datetime(), -20), lead_owner="Administrator"
		)
		res = merge.apply(lead.name, submission("9006", phone), FORM)
		self.assertEqual(res["action"], "alerted")
		self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "status"), ongoing)
		self.assertTrue(
			frappe.db.exists("CRM Task", {"reference_docname": lead.name, "title": "Came back via Meta form"})
		)

	def test_recent_lead_only_updated(self):
		phone = number()
		lead = self.lead(phone)
		self.assertEqual(merge.apply(lead.name, submission("9007", phone), FORM)["action"], "updated")

	def test_old_new_lead_restarts(self):
		phone = number()
		lead = self.lead(phone, created=add_days(now_datetime(), -20))
		self.assertEqual(merge.apply(lead.name, submission("9008", phone), FORM)["action"], "restarted")

	def test_status_changed_after_submission_is_kept(self):
		phone = number()
		submitted = now_datetime() - timedelta(hours=10)
		lead = self.lead(phone, created=submitted - timedelta(minutes=5))
		lost = status_of("Lost")
		lead.status = lost
		lead.lost_reason = frappe.db.get_value("CRM Lost Reason", {}, "name")
		lead.lost_notes = "decided later"
		lead.flags.from_lead_sync = True
		lead.save(ignore_permissions=True)
		res = merge.apply(lead.name, submission("9009", phone, created=submitted), FORM)
		self.assertEqual(res["action"], "kept")
		self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "status"), lost)

	def test_plan_writes_nothing(self):
		phone = number()
		lead = self.lead(phone)
		p = merge.plan(lead.name, submission("9010", phone, job="Owner"), FORM)
		self.assertEqual(p["fill"]["job_title"], "Owner")
		self.assertFalse(frappe.db.get_value("CRM Lead", lead.name, "job_title"))
		self.assertFalse(merge.already_merged("9010"))
