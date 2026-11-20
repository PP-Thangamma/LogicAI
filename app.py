import os
import io
import secrets
from functools import wraps
from datetime import datetime
from flask import Flask,render_template,request,redirect,url_for,flash,session,abort,jsonify,send_file
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename
from database import init_db,get_db
from services.ai_engine import analyze_ticket,recommend_solutions,find_duplicate,upsert_knowledge_from_completed,create_or_join_incident,predict_resolution_hours
from config import Config
from services.assignment import choose_worker
app=Flask(__name__); app.config.from_object(Config); app.config["MAX_CONTENT_LENGTH"]=8*1024*1024
DEPARTMENTS=["Software","Hardware","Electrical","Networking","Maintenance"]
STATUSES=["Open","Seen","Checked","In Progress","Resolved","Completed"]
CAUSE_OPTIONS={
    "Software":["Software bug / application error","Outdated software version","Incorrect configuration","Corrupted application files","Database connection failure","Insufficient system resources"],
    "Hardware":["Loose or damaged connection","Faulty hardware component","Power supply issue","Driver issue","Overheating","Physical damage"],
    "Electrical":["Power interruption","Circuit breaker tripped","Faulty socket / switch","Voltage fluctuation","UPS failure","Wiring issue"],
    "Networking":["Router / access point failure","Network cable disconnected","IP / DNS configuration issue","ISP / internet outage","Wi-Fi interference","Switch or port failure"],
    "Maintenance":["Equipment wear and tear","Blocked drain / leakage","Damaged fixture","Cleaning required","Structural issue","Preventive maintenance overdue"]
}
RESOLUTION_OPTIONS={
    "Software":["Restarted the application / service","Installed software update or patch","Corrected application configuration","Repaired or reinstalled application files","Restored database connection","Freed system resources"],
    "Hardware":["Reconnected or replaced faulty component","Replaced power supply / cable","Installed or updated device driver","Cleaned and cooled the device","Repaired or replaced damaged hardware"],
    "Electrical":["Reset the tripped breaker safely","Restored power supply","Replaced faulty socket / switch","Checked UPS and restored backup","Escalated wiring repair to authorized electrician"],
    "Networking":["Restarted router / access point","Reconnected network cable","Corrected IP / DNS settings","Restored internet service","Reconfigured switch / access point","Resolved Wi-Fi interference"],
    "Maintenance":["Repaired the damaged fixture","Cleared blockage / fixed leakage","Completed cleaning","Replaced faulty fitting","Completed required maintenance work"]
}
with app.app_context(): init_db()
def login_required(fn):
    @wraps(fn)
    def w(*a,**k):
        if not session.get("user_id"): flash("Please sign in.","warning"); return redirect(url_for("login"))
        return fn(*a,**k)
    return w
def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def w(*a,**k):
            if session.get("role") not in roles: abort(403)
            return fn(*a,**k)
        return w
    return deco
@app.context_processor
def globals_():
    if "csrf_token" not in session: session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token":session["csrf_token"],"current_user":session.get("name"),"current_role":session.get("role"),"departments":DEPARTMENTS,"ticket_statuses":STATUSES,"cause_options":CAUSE_OPTIONS,"resolution_options":RESOLUTION_OPTIONS}
def log(db,tid,status,note=""):
    db.execute("INSERT INTO ticket_updates(ticket_id,actor_id,status,note) VALUES(?,?,?,?)",(tid,session.get("user_id"),status,note))
def auto_assign_worker(db, department, category=None, complaint_text=""):
    return choose_worker(db, department, category, complaint_text)


def record_assignment(db, ticket_id, worker_id, reason="Automatic fair assignment"):
    if worker_id:
        db.execute("INSERT INTO assignment_events(ticket_id,worker_id,reason) VALUES(?,?,?)",
                   (ticket_id, worker_id, reason))

def can_access(t):
    r=session.get("role")
    return r=="admin" or (r=="user" and t["user_id"]==session.get("user_id")) or (r=="worker" and (t["department"]==session.get("department") or t["assigned_worker_id"]==session.get("user_id")))
@app.route("/")
def index():
    return redirect(url_for("dashboard")) if session.get("user_id") else render_template("landing.html")
@app.route("/register",methods=["GET","POST"])
def register():
    selected_role=request.values.get("role", "user").lower()
    if selected_role not in ("admin", "worker", "user"):
        abort(400)
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
        department=request.form.get("department","") if selected_role=="worker" else None
        skills=request.form.get("skills","").strip() if selected_role=="worker" else ""
        if not name or not email or len(pw)<8:
            flash("Enter name, email and a password with at least 8 characters.","danger")
            return render_template("register.html",selected_role=selected_role)
        # Admin bootstrap requires a private environment code; never trust a public email address.
        admin_code=os.environ.get("ADMIN_REGISTRATION_CODE", "")
        if selected_role=="admin" and (not admin_code or not secrets.compare_digest(request.form.get("admin_code", ""), admin_code)):
            flash("Administrator registration is disabled or the invitation code is invalid.","danger")
            return render_template("register.html",selected_role=selected_role)
        if selected_role=="worker" and department not in DEPARTMENTS:
            flash("Select your assigned department.","danger")
            return render_template("register.html",selected_role=selected_role)
        try:
            db=get_db()
            cur=db.execute("INSERT INTO users(name,email,password_hash,role,department,skills) VALUES(?,?,?,?,?,?)",(name,email,generate_password_hash(pw),selected_role,department,skills))
            db.commit()
            session.clear(); session.update(user_id=cur.lastrowid,name=name,role=selected_role,department=department)
            return redirect(url_for("dashboard"))
        except Exception:
            flash("That email is already registered.","danger")
    return render_template("register.html",selected_role=selected_role)
@app.route("/login",methods=["GET","POST"])
def login():
    selected_role=request.values.get("role", "user").lower()
    if selected_role not in ("admin", "worker", "user"):
        abort(400)
    if request.method=="POST":
        u=get_db().execute("SELECT * FROM users WHERE email=?",(request.form.get("email","").strip().lower(),)).fetchone()
        if u and u["role"]==selected_role and check_password_hash(u["password_hash"],request.form.get("password","")):
            session.clear(); session.update(user_id=u["id"],name=u["name"],role=u["role"],department=u["department"])
            return redirect(url_for("dashboard"))
        flash("Incorrect email/password, or this account does not belong to the selected role.","danger")
    return render_template("login.html",selected_role=selected_role)
@app.route("/logout",methods=["POST"])
@login_required
def logout(): session.clear(); return redirect(url_for("index"))
def analytics(db):
    def c(sql): return db.execute(sql).fetchone()[0]
    totals={"total":c("SELECT COUNT(*) FROM tickets"),"incidents":c("SELECT COUNT(*) FROM incidents"),"completed":c("SELECT COUNT(*) FROM tickets WHERE status='Completed'"),
    "pending":c("SELECT COUNT(*) FROM tickets WHERE status='Open'"),"seen":c("SELECT COUNT(*) FROM tickets WHERE status='Seen'"),
    "checked":c("SELECT COUNT(*) FROM tickets WHERE status='Checked'"),"in_progress":c("SELECT COUNT(*) FROM tickets WHERE status='In Progress'"),
    "resolved":c("SELECT COUNT(*) FROM tickets WHERE status='Resolved'"),
    "overdue":c("SELECT COUNT(*) FROM tickets WHERE due_at IS NOT NULL AND due_at<CURRENT_TIMESTAMP AND status NOT IN ('Resolved','Completed','Closed')"),
    "avg_rating":db.execute("SELECT ROUND(AVG(rating),1) FROM feedback").fetchone()[0] or 0,
    "avg_resolution_hours":db.execute("SELECT ROUND(AVG((julianday(COALESCE(completed_at,resolved_at))-julianday(created_at))*24),1) FROM tickets WHERE COALESCE(completed_at,resolved_at) IS NOT NULL").fetchone()[0] or 0}
    dept=db.execute("SELECT department,COUNT(*) total FROM tickets GROUP BY department ORDER BY total DESC").fetchall()
    workers=db.execute("""SELECT u.id,u.name,u.department,u.skills,u.availability,
    COUNT(t.id) assigned,
    SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) completed,
    SUM(CASE WHEN t.id IS NOT NULL AND t.status NOT IN ('Resolved','Completed','Closed') THEN 1 ELSE 0 END) active,
    (SELECT COUNT(*) FROM assignment_events ae WHERE ae.worker_id=u.id AND ae.assigned_at>=datetime('now','-30 days')) recent_assigned,
    ROUND(AVG(CASE WHEN t.completed_at IS NOT NULL THEN (julianday(t.completed_at)-julianday(t.created_at))*24 END),1) avg_hours
    FROM users u LEFT JOIN tickets t ON t.assigned_worker_id=u.id WHERE u.role='worker' GROUP BY u.id ORDER BY active ASC,recent_assigned ASC,u.name""").fetchall()
    def period(sql): return db.execute(sql).fetchall()
    daily=period("SELECT date(created_at) period,COUNT(*) total,SUM(status='Completed') completed FROM tickets WHERE created_at>=datetime('now','-6 days') GROUP BY date(created_at) ORDER BY period")
    weekly=period("SELECT strftime('%Y-W%W',created_at) period,COUNT(*) total,SUM(status='Completed') completed FROM tickets WHERE created_at>=datetime('now','-8 weeks') GROUP BY period ORDER BY period")
    monthly=period("SELECT strftime('%Y-%m',created_at) period,COUNT(*) total,SUM(status='Completed') completed FROM tickets WHERE created_at>=datetime('now','-11 months') GROUP BY period ORDER BY period")
    return {"totals":totals,"departments":dept,"workers":workers,"daily":daily,"weekly":weekly,"monthly":monthly}
@app.route("/dashboard")
@login_required
def dashboard():
    db=get_db(); role=session["role"]
    if role not in ("admin", "worker", "user"): abort(403)
    if role=="admin":
        tickets=db.execute("SELECT t.*,u.name reporter,w.name worker FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN users w ON w.id=t.assigned_worker_id ORDER BY t.created_at DESC").fetchall()
        workers=db.execute("SELECT id,name,department,skills,availability FROM users WHERE role='worker' ORDER BY department,name").fetchall()
        return render_template("dashboard.html",view="admin",tickets=tickets,workers=workers,metrics=analytics(db))
    if role=="worker":
        tickets=db.execute("SELECT t.*,u.name reporter FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.department=? OR t.assigned_worker_id=? ORDER BY t.created_at DESC",(session.get("department") or "",session["user_id"])).fetchall()
        worker_profile=db.execute("SELECT skills,availability FROM users WHERE id=?",(session["user_id"],)).fetchone()
        return render_template("dashboard.html",view="worker",tickets=tickets,worker_profile=worker_profile)
    tickets=db.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY created_at DESC",(session["user_id"],)).fetchall()
    return render_template("dashboard.html",view="user",tickets=tickets)
@app.route("/tickets/new",methods=["GET","POST"])
@role_required("user")
def new_ticket():
    if request.method=="POST":
        title=request.form.get("title","").strip(); desc=request.form.get("description","").strip(); loc=request.form.get("location","").strip()
        file=request.files.get("attachment"); fname=None; extracted=""; raw_attachment=None; attachment_mime=None
        if file and file.filename:
            fname=secure_filename(file.filename); ext=fname.rsplit(".",1)[-1].lower() if "." in fname else ""
            if ext not in {"txt","log","csv","md","pdf","png","jpg","jpeg"}: flash("Unsupported attachment type.","danger"); return render_template("new_ticket.html")
            raw=file.read(8*1024*1024)
            raw_attachment=raw
            attachment_mime=file.mimetype or "application/octet-stream"
            if ext in {"txt","log","csv","md"}:
                extracted=raw[:200000].decode("utf-8",errors="ignore")
            elif ext=="pdf":
                try:
                    from pypdf import PdfReader
                    reader=PdfReader(io.BytesIO(raw))
                    extracted="\n".join((page.extract_text() or "") for page in reader.pages[:10])[:200000]
                except Exception:
                    extracted=""
            elif ext in {"png","jpg","jpeg"}:
                try:
                    from PIL import Image
                    import pytesseract
                    extracted=pytesseract.image_to_string(Image.open(io.BytesIO(raw)))[:200000]
                except Exception:
                    extracted=""
        if len(title)<4 or len(desc)<10: flash("Enter a title and at least 10 characters of detail.","danger"); return render_template("new_ticket.html")
        a=analyze_ticket(title+" "+desc,extracted); dept="Admin Review" if a["review_required"] else a["department"]; db=get_db()
        dup=find_duplicate(db,title+" "+desc,category=a["category"])
        worker_id=auto_assign_worker(db,dept,a["category"],title+" "+desc)
        eta_hours,eta_samples,eta_source=predict_resolution_hours(db,a["category"],a["priority"],worker_id)
        cur=db.execute("""INSERT INTO tickets(user_id,title,description,location,category,priority,department,status,duplicate_of,ai_summary,classification_confidence,review_required,attachment_name,attachment_text,attachment_data,attachment_mime,due_at,assigned_worker_id,estimated_hours,estimated_completion_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','+48 hours'),?, ?,datetime('now',?))""",(session["user_id"],title,desc,loc,a["category"],a["priority"],dept,"Open",dup["id"] if dup else None,a["summary"],a["confidence"],int(a["review_required"]),fname,extracted,raw_attachment,attachment_mime,worker_id,eta_hours,f"+{int(eta_hours*60)} minutes"))
        tid=cur.lastrowid
        if worker_id:
            record_assignment(db, tid, worker_id, "Automatic assignment: eligible department, availability, relevant skills (when provided), active workload, recent assignment count and least-recently-assigned tie-break.")
        incident_id,joined=create_or_join_incident(db,tid,dup,title,a["category"],a["priority"],desc)
        log(db,tid,"Open",("Grouped into existing incident #"+str(incident_id)+"." if joined else "New incident group created #"+str(incident_id)+".")+f" AI estimate: {eta_hours} hours ({eta_source}; {eta_samples} historical cases).")
        db.commit()
        flash(f"Ticket #{tid} created · {a['category']} · {a['priority']} priority.","success"); return redirect(url_for("ticket_detail",ticket_id=tid))
    return render_template("new_ticket.html")
@app.route("/tickets/<int:ticket_id>/attachment")
@login_required
def ticket_attachment(ticket_id):
    db=get_db(); t=db.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not t: abort(404)
    if not can_access(t): abort(403)
    if not t["attachment_data"]: abort(404)
    return send_file(io.BytesIO(t["attachment_data"]), mimetype=t["attachment_mime"] or "application/octet-stream",
                     as_attachment=True, download_name=t["attachment_name"] or f"ticket-{ticket_id}-attachment")

@app.route("/tickets/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    db=get_db(); t=db.execute("SELECT t.*,u.name reporter,w.name worker FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN users w ON w.id=t.assigned_worker_id WHERE t.id=?",(ticket_id,)).fetchone()
    if not t: abort(404)
    if not can_access(t): abort(403)
    sol=recommend_solutions(db,t["category"],t["description"]); incident_tickets=db.execute("SELECT id,title,status FROM tickets WHERE incident_id=? ORDER BY created_at",(t["incident_id"],)).fetchall() if t["incident_id"] else []; dup=db.execute("SELECT id,title,status FROM tickets WHERE id=?",(t["duplicate_of"],)).fetchone() if t["duplicate_of"] else None
    updates=db.execute("SELECT x.*,u.name actor FROM ticket_updates x LEFT JOIN users u ON u.id=x.actor_id WHERE x.ticket_id=? ORDER BY x.created_at DESC",(ticket_id,)).fetchall()
    workers=db.execute("SELECT id,name FROM users WHERE role='worker' AND department=? AND COALESCE(availability,'Available')!='Unavailable'",(t["department"],)).fetchall() if session["role"]=="admin" else []
    feedback=db.execute("SELECT * FROM feedback WHERE ticket_id=?",(ticket_id,)).fetchone()
    assignment_history=db.execute("SELECT a.*,u.name worker_name FROM assignment_events a JOIN users u ON u.id=a.worker_id WHERE a.ticket_id=? ORDER BY a.assigned_at DESC,a.id DESC",(ticket_id,)).fetchall()
    return render_template("ticket_detail.html",ticket=t,solutions=sol,duplicate=dup,updates=updates,workers=workers,feedback=feedback,incident_tickets=incident_tickets,assignment_history=assignment_history)
@app.route("/tickets/<int:ticket_id>/assign",methods=["POST"])
@role_required("admin")
def assign_ticket(ticket_id):
    db=get_db(); t=db.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not t: abort(404)
    wid=request.form.get("worker_id") or None; w=db.execute("SELECT * FROM users WHERE id=? AND role='worker'",(wid,)).fetchone() if wid else None
    if wid and (not w or w["department"]!=t["department"] or (w["availability"] or "Available")=="Unavailable"): abort(400)
    eta_hours,_,_=predict_resolution_hours(db,t["category"],t["priority"],wid)
    db.execute("UPDATE tickets SET assigned_worker_id=?,estimated_hours=?,estimated_completion_at=datetime('now',?),updated_at=CURRENT_TIMESTAMP WHERE id=?",(wid,eta_hours,f"+{int(eta_hours*60)} minutes",ticket_id))
    if wid: record_assignment(db, ticket_id, wid, "Admin manual assignment")
    log(db,ticket_id,t["status"],"Assignment changed; estimated resolution time recalculated."); db.commit()
    flash("Assignment updated.","success"); return redirect(url_for("ticket_detail",ticket_id=ticket_id))
@app.route("/worker/profile",methods=["POST"])
@role_required("worker")
def worker_profile():
    skills=request.form.get("skills","").strip()[:300]
    availability=request.form.get("availability","Available")
    if availability not in ("Available","Busy","Unavailable"): abort(400)
    db=get_db(); db.execute("UPDATE users SET skills=?,availability=? WHERE id=?",(skills,availability,session["user_id"])); db.commit()
    flash("Worker availability and expertise updated.","success")
    return redirect(url_for("dashboard"))

@app.route("/tickets/<int:ticket_id>/status",methods=["POST"])
@role_required("admin","worker")
def update_status(ticket_id):
    db=get_db(); t=db.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not t: abort(404)
    if not can_access(t): abort(403)
    if session.get("role")=="worker" and t["assigned_worker_id"]!=session.get("user_id"): abort(403)
    status=request.form.get("status")
    if status not in STATUSES: abort(400)
    current_index = STATUSES.index(t["status"]) if t["status"] in STATUSES else 0
    target_index = STATUSES.index(status)
    if target_index > current_index + 1:
        flash("Please follow the complaint workflow in order: Seen, Checked, In Progress, Resolved, Completed.", "danger")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    if target_index < current_index:
        flash("Status cannot move backwards. Ask Admin to handle a reopening if required.", "danger")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    cause_choice=request.form.get("cause_choice","").strip()
    resolution_choice=request.form.get("resolution_choice","").strip()
    cause=(request.form.get("cause_other","").strip() if cause_choice=="Others" else cause_choice) or request.form.get("cause","").strip()
    resolution=(request.form.get("resolution_other","").strip() if resolution_choice=="Others" else resolution_choice) or request.form.get("resolution","").strip()
    if status=="Completed" and t["status"]!="Resolved":
        flash("Mark the complaint Resolved first, then confirm it as Completed.","danger")
        return redirect(url_for("ticket_detail",ticket_id=ticket_id))
    if status=="Completed" and not resolution:
        flash("Add the verified resolution before marking Completed.","danger")
        return redirect(url_for("ticket_detail",ticket_id=ticket_id))
    stamp=",seen_at=CURRENT_TIMESTAMP" if status=="Seen" else ",checked_at=CURRENT_TIMESTAMP" if status=="Checked" else ",resolved_at=CURRENT_TIMESTAMP" if status=="Resolved" else ",completed_at=CURRENT_TIMESTAMP" if status=="Completed" else ""
    db.execute(f"UPDATE tickets SET status=?,cause=COALESCE(NULLIF(? ,''),cause),resolution=COALESCE(NULLIF(? ,''),resolution),updated_at=CURRENT_TIMESTAMP{stamp} WHERE id=?",(status,cause,resolution,ticket_id))
    log(db,ticket_id,status,request.form.get("note","").strip())
    if status=="Completed": upsert_knowledge_from_completed(db,db.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone())
    if t["incident_id"]:
        group_statuses=[r["status"] for r in db.execute("SELECT status FROM tickets WHERE incident_id=?",(t["incident_id"],)).fetchall()]
        incident_status="Completed" if group_statuses and all(x=="Completed" for x in group_statuses) else "Resolved" if group_statuses and all(x in ("Resolved","Completed") for x in group_statuses) else "In Progress" if any(x=="In Progress" for x in group_statuses) else "Open"
        db.execute("UPDATE incidents SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(incident_status,t["incident_id"]))
    db.commit(); flash("Ticket updated.","success"); return redirect(url_for("ticket_detail",ticket_id=ticket_id))
@app.route("/tickets/<int:ticket_id>/feedback",methods=["POST"])
@role_required("user")
def feedback_ticket(ticket_id):
    db=get_db(); t=db.execute("SELECT * FROM tickets WHERE id=? AND user_id=?",(ticket_id,session["user_id"])).fetchone()
    if not t: abort(404)
    if t["status"] not in ("Resolved","Completed"): abort(400)
    try: rating=int(request.form.get("rating",0))
    except (TypeError, ValueError): abort(400)
    if rating not in range(1,6): abort(400)
    db.execute("""INSERT INTO feedback(ticket_id,user_id,rating,comment) VALUES(?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET rating=excluded.rating,comment=excluded.comment,created_at=CURRENT_TIMESTAMP""",(ticket_id,session["user_id"],rating,request.form.get("comment"," ").strip()))
    db.execute("UPDATE tickets SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(ticket_id,))
    db.commit(); flash("Thanks for your feedback.","success"); return redirect(url_for("ticket_detail",ticket_id=ticket_id))
@app.route("/admin/workers",methods=["POST"])
@role_required("admin")
def create_worker():
    n=request.form.get("name","").strip(); e=request.form.get("email","").strip().lower(); p=request.form.get("password",""); d=request.form.get("department",""); skills=request.form.get("skills","").strip()[:300]
    if not n or not e or len(p)<8 or d not in DEPARTMENTS: flash("Check worker details.","danger"); return redirect(url_for("dashboard"))
    try:
        db=get_db(); db.execute("INSERT INTO users(name,email,password_hash,role,department,skills) VALUES(?,?,?,?,?,?)",(n,e,generate_password_hash(p),"worker",d,skills)); db.commit(); flash("Worker created.","success")
    except Exception: flash("That email already exists.","danger")
    return redirect(url_for("dashboard"))
@app.route("/admin/review/<int:ticket_id>",methods=["POST"])
@role_required("admin")
def review_ticket(ticket_id):
    d=request.form.get("category")
    if d not in DEPARTMENTS: abort(400)
    db=get_db(); ticket=db.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not ticket: abort(404)
    wid=auto_assign_worker(db,d,d,ticket["title"]+" "+ticket["description"])
    chosen=ticket["assigned_worker_id"] or wid
    eta_hours,_,_=predict_resolution_hours(db,d,ticket["priority"],chosen)
    db.execute("UPDATE tickets SET category=?,department=?,assigned_worker_id=?,estimated_hours=?,estimated_completion_at=datetime('now',?),review_required=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",(d,chosen,eta_hours,f"+{int(eta_hours*60)} minutes",ticket_id))
    if chosen: record_assignment(db, ticket_id, chosen, "Assigned after Admin classification review")
    log(db,ticket_id,"Open","Admin approved classification; worker assignment and ETA recalculated."); db.commit()
    return redirect(url_for("ticket_detail",ticket_id=ticket_id))
@app.route("/api/updates")
@login_required
def api_updates():
    db=get_db(); since=request.args.get("since","")
    if session["role"]=="admin": rows=db.execute("SELECT id,status,updated_at FROM tickets WHERE updated_at>=datetime(? ,'-1 second')",(since,)).fetchall()
    elif session["role"]=="worker": rows=db.execute("SELECT id,status,updated_at FROM tickets WHERE department=? AND updated_at>=datetime(? ,'-1 second')",(session.get("department") or "",since)).fetchall()
    else: rows=db.execute("SELECT id,status,updated_at FROM tickets WHERE user_id=? AND updated_at>=datetime(? ,'-1 second')",(session["user_id"],since)).fetchall()
    return jsonify({"updates":[dict(r) for r in rows],"server_time":datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")})
@app.route("/admin/knowledge")
@role_required("admin")
def knowledge():
    articles=get_db().execute("SELECT k.*,COUNT(kl.ticket_id) linked_tickets FROM knowledge_base k LEFT JOIN knowledge_links kl ON kl.knowledge_id=k.id GROUP BY k.id ORDER BY k.updated_at DESC,k.created_at DESC").fetchall()
    return render_template("knowledge.html",articles=articles)
@app.errorhandler(403)
def forbidden(_): return render_template("error.html",code=403,message="You do not have permission to view this page."),403
@app.errorhandler(404)
def not_found(_): return render_template("error.html",code=404,message="The requested page could not be found."),404
@app.errorhandler(400)
def bad_request(_): return render_template("error.html",code=400,message="The submitted request was invalid. Please check the form and try again."),400
@app.before_request
def protect_post_requests():
    if request.method == "POST":
        supplied=request.form.get("csrf_token", "")
        expected=session.get("csrf_token", "")
        if not expected or not supplied or not secrets.compare_digest(supplied, expected):
            abort(400)
@app.teardown_appcontext
def teardown_db(exception=None):
    from database import close_db
    close_db(exception)
if __name__=="__main__": app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1")
