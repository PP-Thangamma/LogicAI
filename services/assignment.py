
"""Fair and workload-balanced worker assignment for LogicAI."""

import re

DEPARTMENTS = {
    "Software",
    "Hardware",
    "Electrical",
    "Networking",
    "Maintenance"
}


def normalize(text):
    """Convert text into searchable words."""
    return set(re.findall(r"[a-z0-9]+", (text or "").casefold()))


def choose_worker(db, department, category=None, complaint_text=""):
    """
    Assignment priority:
    1. Match the department.
    2. Exclude unavailable workers.
    3. Prefer workers with relevant skills.
    4. Select the worker with the lowest active workload.
    5. Break ties using recent assignment count.
    6. Break remaining ties using oldest assignment history.
    """

    if department not in DEPARTMENTS:
        return None

    workers = db.execute(
        """
        SELECT id, skills, availability
        FROM users
        WHERE role = 'worker' AND department = ?
        ORDER BY id
        """,
        (department,)
    ).fetchall()

    if not workers:
        return None

    complaint_words = normalize(
        (category or "") + " " + (complaint_text or "")
    )

    eligible = []

    for worker in workers:

        availability = (
            worker["availability"] or "Available"
        ).strip().casefold()

        # Do not assign work to unavailable workers.
        if availability in ("unavailable", "off duty"):
            continue

        # Available workers get preference over Busy workers.
        availability_rank = (
            0 if availability == "available" else 1
        )

        skills = [
            skill.strip()
            for skill in (worker["skills"] or "").split(",")
            if skill.strip()
        ]

        skill_matches = sum(
            1
            for skill in skills
            if normalize(skill) & complaint_words
        )

        eligible.append({
            "id": worker["id"],
            "availability_rank": availability_rank,
            "skill_matches": skill_matches
        })

    if not eligible:
        return None

    # Prefer Available workers.
    best_availability = min(
        w["availability_rank"] for w in eligible
    )

    eligible = [
        w for w in eligible
        if w["availability_rank"] == best_availability
    ]

    # If at least one worker has relevant skills,
    # prefer workers with the strongest skill match.
    best_skill = max(
        w["skill_matches"] for w in eligible
    )

    if best_skill > 0:
        eligible = [
            w for w in eligible
            if w["skill_matches"] == best_skill
        ]

    ranked_workers = []

    for worker in eligible:

        worker_id = worker["id"]

        # Count currently active tickets.
        active_count = db.execute(
            """
            SELECT COUNT(*)
            FROM tickets
            WHERE assigned_worker_id = ?
            AND status NOT IN (
                'Resolved', 'Completed', 'Closed'
            )
            """,
            (worker_id,)
        ).fetchone()[0]

        # Count assignments during the previous 30 days.
        recent_assignments = db.execute(
            """
            SELECT COUNT(*)
            FROM assignment_events
            WHERE worker_id = ?
            AND assigned_at >= datetime('now', '-30 days')
            """,
            (worker_id,)
        ).fetchone()[0]

        # Find the worker's most recent assignment.
        last_assignment = db.execute(
            """
            SELECT MAX(assigned_at)
            FROM assignment_events
            WHERE worker_id = ?
            """,
            (worker_id,)
        ).fetchone()[0]

        ranked_workers.append((
            (
                active_count,
                recent_assignments,
                last_assignment or "",
                worker_id
            ),
            worker_id
        ))

    # Lowest workload wins. Assignment history breaks ties.
    ranked_workers.sort(key=lambda item: item[0])

    return ranked_workers[0][1]
