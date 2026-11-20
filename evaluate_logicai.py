"""Run a small, transparent smoke evaluation of the rule-based triage engine.
These are synthetic examples, not a substitute for a representative campus dataset.
"""
from services.ai_engine import analyze_ticket, similarity

CASES = [
    ("ERP application crashes after login", "Software"),
    ("Need to install approved software on faculty PC", "Software"),
    ("Browser update fails with application error", "Software"),
    ("Python compiler installation is broken", "Software"),
    ("Database connection failure in ERP app", "Software"),
    ("Laptop keyboard and mouse are not responding", "Hardware"),
    ("Projector monitor screen is blank", "Hardware"),
    ("Printer hardware is not powering on", "Hardware"),
    ("Desktop computer battery and power button issue", "Hardware"),
    ("RAM issue causes blue screen on laptop", "Hardware"),
    ("Classroom socket has voltage fluctuation", "Electrical"),
    ("Circuit breaker tripped in the lab", "Electrical"),
    ("UPS power supply interruption", "Electrical"),
    ("Damaged electrical wiring near classroom", "Electrical"),
    ("Power outage in the computer lab", "Electrical"),
    ("Campus Wi-Fi router is disconnected", "Networking"),
    ("LAN ethernet connection and DNS failure", "Networking"),
    ("Internet access point connectivity is down", "Networking"),
    ("Network switch port is not working", "Networking"),
    ("Wi-Fi interference causes slow network", "Networking"),
    ("Water leakage near the computer lab", "Maintenance"),
    ("Classroom door and window need repair", "Maintenance"),
    ("Cleaning and facility maintenance required", "Maintenance"),
    ("Ceiling leakage and plumbing issue", "Maintenance"),
    ("Damaged furniture in classroom", "Maintenance"),
]


def main():
    correct = 0
    for text, expected in CASES:
        actual = analyze_ticket(text)["category"]
        correct += actual == expected
        print(f"{'PASS' if actual == expected else 'CHECK'} | expected={expected:12} predicted={actual:12} | {text}")
    print(f"\nSynthetic category accuracy: {correct}/{len(CASES)} = {correct/len(CASES):.1%}")
    pairs = [
        ("Campus Wi-Fi is not working in Block B", "Students cannot connect to campus Wi-Fi in Block B"),
        ("ERP crashes after login", "The application fails when signing into ERP"),
    ]
    print("\nSimilarity smoke checks:")
    for a, b in pairs:
        print(f"{similarity(a,b):.3f} | {a} <> {b}")
    print("\nNote: synthetic smoke-test scores do not represent real-world model accuracy.")

if __name__ == "__main__":
    main()
