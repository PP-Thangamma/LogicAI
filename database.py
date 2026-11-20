import sqlite3
from flask import current_app, g
def get_db():
    if "db" not in g:
        g.db=sqlite3.connect(current_app.config["DATABASE"], timeout=15); g.db.row_factory=sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=15000")
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db
def _cols(db,t): return {r["name"] for r in db.execute(f"PRAGMA table_info({t})")}
def _add(db,t,d):
    if d.split()[0] not in _cols(db,t): db.execute(f"ALTER TABLE {t} ADD COLUMN {d}")
def init_db():
    db=get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),title TEXT NOT NULL,description TEXT NOT NULL,location TEXT,category TEXT NOT NULL,priority TEXT NOT NULL,department TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Open',duplicate_of INTEGER REFERENCES tickets(id),ai_summary TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS knowledge_base(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,category TEXT NOT NULL,solution TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    for d in ["department TEXT", "skills TEXT DEFAULT ''", "availability TEXT DEFAULT 'Available'"]: _add(db,"users",d)
    for d in ["assigned_worker_id INTEGER REFERENCES users(id)","classification_confidence REAL DEFAULT 0","review_required INTEGER DEFAULT 0","cause TEXT","resolution TEXT","attachment_name TEXT","attachment_text TEXT","attachment_data BLOB","attachment_mime TEXT","seen_at TEXT","checked_at TEXT","resolved_at TEXT","completed_at TEXT","due_at TEXT", "incident_id INTEGER REFERENCES incidents(id)", "estimated_hours REAL", "estimated_completion_at TEXT"]: _add(db,"tickets",d)
    for d in ["cause TEXT","source_ticket_id INTEGER REFERENCES tickets(id)","updated_at TEXT"]: _add(db,"knowledge_base",d)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ticket_updates(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,actor_id INTEGER REFERENCES users(id),status TEXT NOT NULL,note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE,user_id INTEGER NOT NULL REFERENCES users(id),rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),comment TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS knowledge_links(id INTEGER PRIMARY KEY AUTOINCREMENT,knowledge_id INTEGER NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,UNIQUE(knowledge_id,ticket_id));
    CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,category TEXT NOT NULL,priority TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Open',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS assignment_events(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,worker_id INTEGER NOT NULL REFERENCES users(id),reason TEXT NOT NULL DEFAULT '',assigned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')));
    CREATE INDEX IF NOT EXISTS idx_assignment_worker_time ON assignment_events(worker_id,assigned_at);
    INSERT INTO assignment_events(ticket_id,worker_id,reason,assigned_at)
      SELECT t.id,t.assigned_worker_id,'Migrated existing assignment',COALESCE(t.updated_at,CURRENT_TIMESTAMP)
      FROM tickets t WHERE t.assigned_worker_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM assignment_events a WHERE a.ticket_id=t.id);
    CREATE INDEX IF NOT EXISTS idx_tickets_dept_status ON tickets(department,status);
    CREATE INDEX IF NOT EXISTS idx_tickets_worker ON tickets(assigned_worker_id);
    CREATE INDEX IF NOT EXISTS idx_tickets_incident ON tickets(incident_id);
    """)
    if db.execute("SELECT COUNT(*) FROM knowledge_base").fetchone()[0]==0:
        db.executemany("INSERT INTO knowledge_base(title,category,solution) VALUES(?,?,?)",[
        ("Wi-Fi troubleshooting","Networking","Check campus SSID, toggle Wi-Fi, forget and rejoin. If multiple users are affected, inspect the access point and switch."),
        ("Computer will not power on","Hardware","Check power cable and outlet, disconnect peripherals and retry. Escalate persistent failure."),
        ("Keyboard or mouse not working","Hardware","Reconnect cable or receiver, try another USB port and test a known-good peripheral."),
        ("Application installation failure","Software","Confirm compatibility and disk space, use the approved software portal and capture the exact error."),
        ("Electrical power interruption","Electrical","Check UPS status and breaker indicators; do not open electrical panels. Escalate to authorized Electrical staff."),
        ("Facility or plumbing issue","Maintenance","Restrict access to affected area and notify authorized Maintenance staff.")])
    # Backfill incident groups for tickets already in the database.
    for row in db.execute("SELECT id,title,category,priority,description,status FROM tickets WHERE incident_id IS NULL").fetchall():
        cur=db.execute("INSERT INTO incidents(title,category,priority,description,status) VALUES(?,?,?,?,?)",(row["title"],row["category"],row["priority"],row["description"],row["status"]))
        db.execute("UPDATE tickets SET incident_id=? WHERE id=?",(cur.lastrowid,row["id"]))
    db.commit()
def close_db(_=None):
    db=g.pop("db",None)
    if db is not None: db.close()
