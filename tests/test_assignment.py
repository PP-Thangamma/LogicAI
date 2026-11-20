import sqlite3
import unittest
from services.assignment import choose_worker

class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE users(id INTEGER PRIMARY KEY, role TEXT, department TEXT, skills TEXT, availability TEXT);
          CREATE TABLE tickets(id INTEGER PRIMARY KEY, assigned_worker_id INTEGER, status TEXT);
          CREATE TABLE assignment_events(id INTEGER PRIMARY KEY, ticket_id INTEGER, worker_id INTEGER, reason TEXT, assigned_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        self.db.executemany('INSERT INTO users VALUES(?,?,?,?,?)', [
            (1,'worker','Software','ERP, Python','Available'),
            (2,'worker','Software','ERP, Python','Available'),
            (3,'worker','Software','ERP, Python','Unavailable'),
            (4,'worker','Networking','Wi-Fi, Router','Available'),
        ])

    def tearDown(self):
        self.db.close()

    def test_never_assigns_outside_department(self):
        self.assertIn(choose_worker(self.db, 'Software', 'Software', 'ERP error'), (1,2))

    def test_excludes_unavailable_worker(self):
        self.db.execute("UPDATE users SET availability='Unavailable' WHERE id IN (1,2)")
        self.assertIsNone(choose_worker(self.db, 'Software', 'Software', 'ERP error'))

    def test_available_preferred_over_busy(self):
        self.db.execute("UPDATE users SET availability='Busy' WHERE id=1")
        self.assertEqual(choose_worker(self.db, 'Software', 'Software', 'ERP error'), 2)

    def test_skill_match_preferred_when_present(self):
        self.db.execute("UPDATE users SET skills='Printers' WHERE id=1")
        self.db.execute("UPDATE users SET skills='ERP, Python' WHERE id=2")
        self.assertEqual(choose_worker(self.db, 'Software', 'Software', 'ERP application error'), 2)

    def test_lower_active_workload_preferred(self):
        self.db.executemany('INSERT INTO tickets(assigned_worker_id,status) VALUES(?,?)', [(1,'Open'),(1,'In Progress')])
        self.assertEqual(choose_worker(self.db, 'Software', 'Software', 'ERP error'), 2)

    def test_round_robin_tie_breaks_by_oldest_assignment(self):
        self.db.execute("INSERT INTO assignment_events(ticket_id,worker_id,reason,assigned_at) VALUES(1,1,'test',datetime('now'))")
        self.db.execute("INSERT INTO assignment_events(ticket_id,worker_id,reason,assigned_at) VALUES(2,2,'test',datetime('now','-1 day'))")
        self.assertEqual(choose_worker(self.db, 'Software', 'Software', 'ERP error'), 2)

if __name__ == '__main__':
    unittest.main()
