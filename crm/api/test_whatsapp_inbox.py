import random
from unittest.mock import patch

import frappe

try:  # v16: test records load lazily
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # v15
	from frappe.tests.utils import FrappeTestCase as TestCase
from frappe.utils import add_to_date, now_datetime

from crm.api import whatsapp, whatsapp_inbox as inbox

ACCOUNT = "CRM Inbox Test Account"
REP = "wa-inbox-rep@example.com"
OTHER = "wa-inbox-other@example.com"


def number() -> str:
	return "88017" + "".join(random.choice("0123456789") for _ in range(8))


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0, "roles": [{"role": "Sales User"}]}
		).insert(ignore_permissions=True)


class TestWhatsAppInbox(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if "frappe_whatsapp" not in frappe.get_installed_apps():
			raise __import__("unittest").SkipTest("frappe_whatsapp is not installed")
		inbox.ensure_fields()
		if not frappe.db.exists("WhatsApp Account", ACCOUNT):
			frappe.get_doc(
				{
					"doctype": "WhatsApp Account",
					"account_name": ACCOUNT,
					"phone_id": "crm-inbox-test-phone",
					"business_id": "crm-inbox-test-waba",
					"status": "Active",
					"url": "https://graph.facebook.com",
					"version": "v25.0",
				}
			).insert(ignore_permissions=True)
		for u in (REP, OTHER):
			_user(u)

	def setUp(self):
		# the CRM's own behaviour only: no site app's crm_whatsapp_incoming hook (those have their own tests)
		self.incoming_hooks = []
		orig = frappe.get_hooks

		def hooks(name=None, *args, **kwargs):
			if name == "crm_whatsapp_incoming":
				return self.incoming_hooks
			return orig(name, *args, **kwargs)

		self._hooks = patch.object(frappe, "get_hooks", side_effect=hooks)
		self._hooks.start()

	def tearDown(self):
		self._hooks.stop()
		frappe.set_user("Administrator")

	def incoming(self, sender, text="hello", **extra):
		return frappe.get_doc(
			{
				"doctype": "WhatsApp Message",
				"type": "Incoming",
				"from": sender,
				"message": text,
				"message_id": "wamid.test." + frappe.generate_hash(length=12),
				"content_type": "text",
				"profile_name": "Test Sender",
				"whatsapp_account": ACCOUNT,
				**extra,
			}
		).insert(ignore_permissions=True)

	def conversation(self, sender):
		return frappe.db.get_value(
			"CRM WhatsApp Conversation", {"whatsapp_account": ACCOUNT, "contact_number": inbox.normalize_number(sender)}
		)

	def test_number_forms(self):
		self.assertEqual(inbox.normalize_number("+880 1712-345678"), "8801712345678")
		self.assertEqual(inbox.normalize_number("8801712345678"), "8801712345678")
		self.assertEqual(inbox.normalize_number("008801712345678"), "8801712345678")
		if inbox._default_region() == "BD":
			self.assertEqual(inbox.normalize_number("01712345678"), "8801712345678")
		self.assertEqual(inbox.normalize_number(""), "")

	def test_incoming_builds_one_conversation(self):
		sender = number()
		first = self.incoming(sender, "hi")
		self.incoming(sender, "are you there?")
		name = self.conversation(sender)
		self.assertTrue(name)
		conv = frappe.get_doc("CRM WhatsApp Conversation", name)
		self.assertEqual(conv.unread, 2)
		self.assertEqual(conv.last_message, "are you there?")
		self.assertEqual(conv.profile_name, "Test Sender")
		self.assertTrue(inbox.window_open(conv.last_incoming_at))
		self.assertEqual(frappe.db.get_value("WhatsApp Message", first.name, inbox.FIELD), name)
		self.assertEqual(len(inbox.get_thread(name)), 2)
		inbox.mark_read(name)
		self.assertEqual(frappe.db.get_value("CRM WhatsApp Conversation", name, "unread"), 0)

	def test_reply_leaves_from_the_number_written_to(self):
		sender = number()
		self.incoming(sender)
		self.assertEqual(inbox.account_for(number="+" + sender), ACCOUNT)

	def test_receive_only_and_window(self):
		sender = number()
		self.incoming(sender)
		name = self.conversation(sender)
		with self.assertRaises(frappe.ValidationError):
			inbox.send(name, "hello")  # no token on the test account: receive-only
		frappe.db.set_value("CRM WhatsApp Conversation", name, "last_incoming_at", add_to_date(now_datetime(), hours=-30))
		self.assertFalse(inbox.window_open(frappe.db.get_value("CRM WhatsApp Conversation", name, "last_incoming_at")))
		with patch.object(inbox, "can_send", return_value=True), self.assertRaises(frappe.ValidationError):
			inbox.send(name, "hello")  # outside 24 h: template only

	def test_outgoing_clears_unread(self):
		sender = number()
		self.incoming(sender)
		name = self.conversation(sender)
		with patch(
			"frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message.WhatsAppMessage.notify",
			lambda self, data: setattr(self, "message_id", "wamid.out." + frappe.generate_hash(length=8)),
		), patch.object(inbox, "can_send", return_value=True):
			inbox.send(name, "hello back")
		conv = frappe.get_doc("CRM WhatsApp Conversation", name)
		self.assertEqual(conv.unread, 0)
		self.assertEqual(conv.last_direction, "Outgoing")
		self.assertEqual(len(inbox.get_thread(name)), 2)

	def test_visibility(self):
		sender = number()
		self.incoming(sender)
		name = self.conversation(sender)
		frappe.set_user(REP)
		self.assertIn(name, [r.name for r in inbox.list_conversations(limit=500)])  # unlinked: every sales user
		frappe.set_user("Administrator")
		frappe.db.set_value("CRM WhatsApp Conversation", name, "owner_user", OTHER)
		frappe.set_user(REP)
		self.assertNotIn(name, [r.name for r in inbox.list_conversations(limit=500)])
		with self.assertRaises(frappe.PermissionError):
			inbox.get_thread(name)
		frappe.set_user(OTHER)
		self.assertIn(name, [r.name for r in inbox.list_conversations(scope="mine", limit=500)])

	def test_link_and_create_lead(self):
		sender = number()
		msg = self.incoming(sender)
		name = self.conversation(sender)
		lead = inbox.create_lead(name)
		self.assertEqual(frappe.db.get_value("CRM WhatsApp Conversation", name, "reference_name"), lead)
		self.assertEqual(frappe.db.get_value("WhatsApp Message", msg.name, "reference_name"), lead)
		self.assertEqual(inbox.normalize_number(frappe.db.get_value("CRM Lead", lead, "mobile_no")), sender)

	def test_hooks(self):
		sender = number()
		self.incoming_hooks = ["crm.api.test_whatsapp_inbox.broken_hook"]
		msg = self.incoming(sender)  # a failing hook never loses the message
		self.assertTrue(frappe.db.exists("WhatsApp Message", msg.name))
		self.assertTrue(self.conversation(sender))
		# a hook's (doctype, name) links the message and its conversation
		lead = frappe.get_doc({"doctype": "CRM Lead", "first_name": "Hooked", "mobile_no": "+" + number()}).insert(
			ignore_permissions=True
		)
		frappe.flags.test_hook_lead = lead.name
		self.incoming_hooks = ["crm.api.test_whatsapp_inbox.linking_hook"]
		other = number()
		msg = self.incoming(other)
		self.assertEqual((msg.reference_doctype, msg.reference_name), ("CRM Lead", lead.name))
		self.assertEqual(frappe.db.get_value("CRM WhatsApp Conversation", self.conversation(other), "reference_name"), lead.name)


def broken_hook(doc):
	raise RuntimeError("boom")


def linking_hook(doc):
	return "CRM Lead", frappe.flags.test_hook_lead
