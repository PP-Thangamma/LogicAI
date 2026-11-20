import sqlite3
import unittest
from services.ai_engine import create_or_join_incident, predict_resolution_hours, upsert_knowledge_from_completed, find_duplicate

class InnovationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE incidents(id INTEGER PRIMARY KEY, title TEXT, category TEXT, priority TEXT, description TEXT, status TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE tickets(id INTEGER PRIMARY KEY, title TEXT, description TEXT, status TEXT, incident_id INTEGER, category TEXT, priority TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT, completed_at TEXT, assigned_worker_id INTEGER);
        ''')

    def tearDown(self):
        self.db.close()

    def test_duplicate_ticket_joins_existing_incident(self):
        self.db.execute("INSERT INTO incidents(title,category,priority,description,status) VALUES('Wi-Fi down','Networking','High','Campus Wi-Fi is down','Open')")
        incident_id = self.db.execute('SELECT id FROM incidents').fetchone()['id']
        self.db.execute("INSERT INTO tickets(id,title,description,status,incident_id,category,priority) VALUES(1,'Wi-Fi down','Campus Wi-Fi is down','Open',?,'Networking','High')", (incident_id,))
        duplicate = self.db.execute('SELECT id,title,description,status,incident_id FROM tickets WHERE id=1').fetchone()
        self.db.execute("INSERT INTO tickets(id,title,description,status,category,priority) VALUES(2,'Wi-Fi down','Campus Wi-Fi is down','Open','Networking','High')")
        joined_id, joined = create_or_join_incident(self.db, 2, duplicate, 'Wi-Fi down', 'Networking', 'High', 'Campus Wi-Fi is down')
        self.assertTrue(joined)
        self.assertEqual(joined_id, incident_id)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM tickets WHERE incident_id=?', (incident_id,)).fetchone()[0], 2)

    def test_eta_has_safe_fallback_without_history(self):
        hours, samples, source = predict_resolution_hours(self.db, 'Software', 'High')
        self.assertGreater(hours, 0)
        self.assertEqual(samples, 0)
        self.assertIn('insufficient history', source)

    def test_eta_uses_historical_resolutions(self):
        for _ in range(3):
            self.db.execute("INSERT INTO tickets(category,priority,created_at,completed_at,status) VALUES('Software','High',datetime('now','-5 hours'),datetime('now','-1 hour'),'Completed')")
        hours, samples, source = predict_resolution_hours(self.db, 'Software', 'High')
        self.assertEqual(samples, 3)
        self.assertEqual(source, 'category and priority history')
        self.assertAlmostEqual(hours, 3.4, places=1)

    def test_eta_median_is_resistant_to_outlier(self):
        for duration in (2, 3, 4, 80):
            self.db.execute("INSERT INTO tickets(category,priority,created_at,completed_at,status) VALUES('Hardware','Medium',datetime('now',?),datetime('now'),'Completed')", (f'-{duration} hours',))
        hours, samples, source = predict_resolution_hours(self.db, 'Hardware', 'Medium')
        self.assertEqual(samples, 4)
        self.assertAlmostEqual(hours, 3.5, places=1)

    def test_category_filter_duplicate_lookup(self):
        self.db.execute("INSERT INTO tickets(id,title,description,status,category,priority) VALUES(10,'Wi-Fi down','Campus Wi-Fi is down','Open','Networking','High')")
        self.assertIsNotNone(find_duplicate(self.db, 'Campus Wi-Fi is down in block B', category='Networking'))
        self.assertIsNone(find_duplicate(self.db, 'Campus Wi-Fi is down in block B', category='Software'))

    def test_knowledge_base_rejects_uncompleted_ticket(self):
        self.db.executescript("CREATE TABLE knowledge_base(id INTEGER PRIMARY KEY, title TEXT, category TEXT, solution TEXT, cause TEXT, source_ticket_id INTEGER, updated_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE knowledge_links(id INTEGER PRIMARY KEY, knowledge_id INTEGER, ticket_id INTEGER, UNIQUE(knowledge_id,ticket_id));")
        ticket = {'status':'Resolved','title':'ERP down','category':'Software','cause':'Server error','resolution':'Restarted service','description':'ERP application unavailable','id':1}
        with self.assertRaises(ValueError):
            upsert_knowledge_from_completed(self.db, ticket)

if __name__ == '__main__':
    unittest.main()
