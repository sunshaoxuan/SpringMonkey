import sqlite3
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock, patch

import gmail_autolabel as worker


class AutolabelTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.gmail = Mock()
        self.gmail.cursor.return_value = "100"
        worker.initialize(self.db, self.gmail)
        started = self.db.execute("SELECT started_ms FROM checkpoint").fetchone()[0]
        self.new = {"internalDate": str(started), "labelIds": ["INBOX"]}
        self.old = {"internalDate": str(started - 1), "labelIds": ["INBOX"]}
        self.gmail.user_labels.return_value = {"Label_1": "Invoices"}

    def test_replayed_events_and_preexisting_labels(self):
        self.gmail.messages.return_value = ({"fresh", "old", "labeled", "ambiguous", "spam"}, "101")
        worker.collect(self.db, self.gmail)
        self.gmail.metadata.side_effect = {
            "fresh": self.new,
            "old": self.old,
            "labeled": self.new | {"labelIds": ["INBOX", "Label_2"]},
            "ambiguous": self.new | {"ambiguous": True},
            "spam": self.new | {"labelIds": ["INBOX", "SPAM"]},
        }.get
        classify = lambda data, _labels: None if data.get("ambiguous") else "Label_1"
        worker.process(self.db, self.gmail, classify)
        worker.collect(self.db, self.gmail)
        worker.process(self.db, self.gmail, classify)
        self.gmail.add_label.assert_called_once_with("fresh", "Label_1", {"Label_1": "Invoices"})
        self.assertEqual(self.db.execute("SELECT history_id FROM checkpoint").fetchone(), ("101",))
        self.assertEqual(self.db.execute("SELECT count(*) FROM messages").fetchone(), (5,))

    def test_expired_history_recovers_pending_without_advancing_on_failure(self):
        error = HTTPError("https://gmail.googleapis.com/", 404, "expired", {}, None)
        self.gmail.cursor.return_value = "105"
        self.gmail.messages.side_effect = [error, RuntimeError("recover failed")]
        with self.assertRaises(RuntimeError):
            worker.collect(self.db, self.gmail)
        self.assertEqual(self.db.execute("SELECT history_id FROM checkpoint").fetchone(), ("100",))
        self.gmail.messages.side_effect = [error, ({"replayed"}, None)]
        worker.collect(self.db, self.gmail)
        self.assertEqual(self.db.execute("SELECT history_id FROM checkpoint").fetchone(), ("105",))
        self.assertEqual(self.db.execute("SELECT id, outcome FROM messages").fetchone(), ("replayed", None))

    def test_only_allowed_additive_write(self):
        gmail = worker.Gmail({})
        allowed = {"Label_1": "Invoices"}
        with patch.object(gmail, "headers", return_value={}), patch.object(worker, "request_json") as req:
            for label in ("INBOX", "TRASH", "Label_other"):
                with self.assertRaises(ValueError):
                    gmail.add_label("test", label, allowed)
            with self.assertRaises(ValueError):
                gmail.add_label("../test", "Label_1", allowed)
            req.assert_not_called()
            gmail.add_label("test", "Label_1", allowed)
            req.assert_called_once_with(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/test/modify",
                headers={"Content-Type": "application/json"}, body={"addLabelIds": ["Label_1"]},
            )

    def test_model_cannot_select_unlisted_or_system_label(self):
        with patch.object(worker, "request_json") as req:
            req.return_value = {"choices": [{"message": {"content": '{"label_id":"TRASH"}'}}]}
            self.assertIsNone(worker.choose_label("synthetic", {}, {"Label_1": "Invoices"}))
            self.assertNotIn("snippet", str(req.call_args.kwargs["body"]))


if __name__ == "__main__":
    unittest.main()
