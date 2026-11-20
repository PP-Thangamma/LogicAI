import re
from difflib import SequenceMatcher
RULES={
"Software":["software","application","app","install","installation","crash","update","license","program","browser","compiler"],
"Hardware":["keyboard","mouse","monitor","screen","laptop","desktop","computer","computers","pc","printer","power button","battery","blue screen","hardware","cpu","ram"],
"Electrical":["electric","electrical","power outage","power cut","short circuit","socket","switchboard","voltage","wiring","fuse","breaker","ups"],
"Networking":["wifi","wi-fi","internet","lan","ethernet","network","router","access point","connectivity","no connection","switch"],
"Maintenance":["maintenance","water leak","leakage","cleaning","furniture","door","window","ceiling","plumbing","facility"]}
def tokenize(s):
    text=(s or "").lower()
    phrase_map={
        "not working":" failure ", "does not work":" failure ", "isn't working":" failure ",
        "cannot connect":" connectivity ", "can't connect":" connectivity ", "not connecting":" connectivity ",
        "disconnected":" connectivity ", "crashes":" failure ", "crash":" failure ",
        "fails":" failure ", "failed":" failure ", "failure":" failure ",
        "wireless":" wifi ", "wi-fi":" wifi ", "app":" application ", "signing into":" login ",
    }
    for old,new in phrase_map.items(): text=text.replace(old,new)
    stop={"the","a","an","is","are","was","were","to","of","in","on","for","and","or","after","when","with","my","our","their","this","that","into","cannot","not"}
    return [token for token in re.findall(r"[a-z0-9]+",text) if token not in stop]
def analyze_ticket(text,attachment_text=""):
    s=f"{text or ''} {attachment_text or ''}".lower().replace("wi-fi", "wifi")
    def matches(term):
        if " " in term or "-" in term:
            pattern=r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
            return bool(re.search(pattern, s))
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", s))
    scores={c:sum(1 + 1.5*term.count(" ") for term in terms if matches(term)) for c,terms in RULES.items()}
    ranked=sorted(scores.items(),key=lambda x:x[1],reverse=True)
    category=ranked[0][0] if ranked and ranked[0][1] else "General IT"
    best=ranked[0][1] if ranked else 0; total=sum(scores.values())
    confidence=min(.98,.48+best/max(1,total)*.35+min(best,3)*.05) if best else .25
    if len(ranked)>1 and ranked[0][1]==ranked[1][1]: confidence=min(confidence,.55)
    critical=["entire campus","whole college","everyone","all users","outage","server down","all computers","entire lab"]
    high=["urgent","cannot work","can't work","multiple users","deadline","exam","classroom","major failure","complete failure"]
    medium=["not working","unable","failed","error","slow","intermittent"]
    priority="Critical" if any(x in s for x in critical) else "High" if any(x in s for x in high) else "Medium" if any(x in s for x in medium) else "Low"
    summary=" ".join((text or "").split())[:177]
    return {"category":category,"priority":priority,"department":category if category!="General IT" else "Admin Review",
            "confidence":round(confidence,2),"review_required":confidence<.60,"summary":summary}
def similarity(a,b):
    x,y=set(tokenize(a)),set(tokenize(b))
    jac=len(x&y)/max(1,len(x|y))
    seq=SequenceMatcher(None," ".join(tokenize(a))," ".join(tokenize(b))).ratio()
    return .65*jac+.35*seq
def find_duplicate(db,text,threshold=.48,category=None):
    # Restrict matching to the same predicted category to reduce false incident merges.
    if category:
        rows=db.execute("SELECT id,title,description,status,incident_id FROM tickets WHERE category=? AND status NOT IN ('Closed','Completed') ORDER BY id DESC LIMIT 500",(category,)).fetchall()
    else:
        rows=db.execute("SELECT id,title,description,status,incident_id FROM tickets WHERE status NOT IN ('Closed','Completed') ORDER BY id DESC LIMIT 500").fetchall()
    best=None; score=0
    for r in rows:
        v=similarity(text,r["title"]+" "+r["description"])
        if v>score: best,score=r,v
    return best if best and score>=threshold else None
def recommend_solutions(db,category,description,limit=5):
    rows=db.execute("SELECT id,title,category,solution,cause FROM knowledge_base").fetchall()
    ranked=[]
    for r in rows:
        s=similarity(description,r["title"]+" "+r["solution"]+" "+(r["cause"] or "")) + (.22 if r["category"].lower()==category.lower() else 0)
        ranked.append((s,r))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return [{"id":r["id"],"title":r["title"],"category":r["category"],"cause":r["cause"] or "Not recorded","solution":r["solution"],"score":round(s,2)} for s,r in ranked[:limit] if s>.05]
def upsert_knowledge_from_completed(db,t):
    if t["status"] != "Completed":
        raise ValueError("Knowledge articles can only be created from Completed tickets.")
    title,cat=t["title"],t["category"]; cause=t["cause"] or "Not specified"; solution=t["resolution"] or ""
    rows=db.execute("SELECT * FROM knowledge_base WHERE category=?",(cat,)).fetchall()
    best=None; score=0
    for r in rows:
        v=similarity(title+" "+t["description"]+" "+solution,r["title"]+" "+r["solution"]+" "+(r["cause"] or ""))
        if v>score: best,score=r,v
    if best and score>=.58:
        merged=best["solution"] if solution.lower() in best["solution"].lower() else best["solution"].rstrip()+"\n\nAdditional verified resolution: "+solution
        db.execute("UPDATE knowledge_base SET solution=?,cause=COALESCE(cause,?),updated_at=CURRENT_TIMESTAMP WHERE id=?",(merged,cause,best["id"]))
        kid=best["id"]
    else:
        kid=db.execute("INSERT INTO knowledge_base(title,category,solution,cause,source_ticket_id,updated_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)",(title,cat,solution,cause,t["id"])).lastrowid
    db.execute("INSERT OR IGNORE INTO knowledge_links(knowledge_id,ticket_id) VALUES(?,?)",(kid,t["id"]))
    return kid


def create_or_join_incident(db, ticket_id, duplicate, title, category, priority, description):
    """Put semantically similar tickets into one shared incident group."""
    if duplicate:
        incident_id=duplicate["incident_id"] if "incident_id" in duplicate.keys() else None
        if not incident_id:
            cur=db.execute("INSERT INTO incidents(title,category,priority,description,status) VALUES(?,?,?,?,?)",(duplicate["title"],category,priority,duplicate["description"],duplicate["status"]))
            incident_id=cur.lastrowid
            db.execute("UPDATE tickets SET incident_id=? WHERE id=?",(incident_id,duplicate["id"]))
        db.execute("UPDATE incidents SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(incident_id,))
        db.execute("UPDATE tickets SET incident_id=? WHERE id=?",(incident_id,ticket_id))
        return incident_id, True
    cur=db.execute("INSERT INTO incidents(title,category,priority,description,status) VALUES(?,?,?,?,?)",(title,category,priority,description,"Open"))
    incident_id=cur.lastrowid
    db.execute("UPDATE tickets SET incident_id=? WHERE id=?",(incident_id,ticket_id))
    return incident_id, False


def predict_resolution_hours(db, category, priority, worker_id=None):
    """Robust historical ETA using median completed-ticket duration.

    Matching category+priority is preferred when at least two examples exist;
    otherwise category history, then all-category history, then an explicitly
    labelled 24-hour cold-start estimate is used. Median reduces outlier impact.
    """
    from statistics import median

    def durations(where, params=()):
        rows=db.execute(f"""SELECT (julianday(COALESCE(completed_at,resolved_at))-julianday(created_at))*24 AS hrs
            FROM tickets WHERE {where} AND COALESCE(completed_at,resolved_at) IS NOT NULL
            AND julianday(COALESCE(completed_at,resolved_at))>=julianday(created_at)""",params).fetchall()
        values=[float(r["hrs"]) for r in rows if r["hrs"] is not None and float(r["hrs"])>0]
        return values

    values=durations("category=? AND priority=?",(category,priority))
    source="category and priority history"
    if len(values)<2:
        values=durations("category=?",(category,))
        source="category history"
    if not values:
        values=durations("1=1")
        source="overall history" if values else "initial estimate (insufficient history)"
    hours=median(values) if values else 24.0
    factor={"Critical":0.75,"High":0.85,"Medium":1.0,"Low":1.15}.get(priority,1.0)
    hours=float(hours)*factor
    if worker_id:
        load=db.execute("SELECT COUNT(*) FROM tickets WHERE assigned_worker_id=? AND status NOT IN ('Resolved','Completed','Closed')",(worker_id,)).fetchone()[0]
        hours *= 1.0 + min(load,8)*0.08
    return round(max(1.0,min(hours,240.0)),1),len(values),source

