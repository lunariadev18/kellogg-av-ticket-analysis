"""
Synthetic ServiceNow-style AV support ticket generator.

Generates a realistic (but fully synthetic) dataset of classroom AV/IT
support tickets for a university business school. All room numbers,
technician names, requester IDs, and ticket contents are fictional.
No real ticket records are included or reproduced.

CALIBRATION: the generator's distributions (volume, seasonality, weekday and
hour-of-day profiles, issue mix, resolution-time percentiles, missing-room
rate, open rate, technician concentration) are tuned to match AGGREGATE
statistics measured from a real ServiceNow export that is NOT part of this
repository. Only summary statistics informed these constants — no raw rows,
identifiers, or free text were carried over.

What the raw export contains (mirroring a real instance):
  - ~75% scheduling-automation rows created by the 25Live room-booking
    integration (category "Classroom Scheduling") — noise the analysis
    must filter out
  - ~660 human-submitted AV support tickets over 18 months
  - ~30% of human tickets missing the room number (building-level only)
  - resolution timestamps measured in CALENDAR time (queue time included):
    roughly a quarter resolved within the hour, half taking > 24 hours
  - ~5% open tickets, inconsistent category casing, whitespace-padded
    room IDs, occasional double-submitted duplicates

Planted analytical signal (the pattern the analysis is designed to find):
  Five classrooms share a legacy HDMI matrix switcher configuration
  ("legacy_matrix_v1") with auto-input-switching disabled. These rooms
  generate a disproportionate share of display-signal tickets, clustered
  at first-class-of-day times, with elevated repeat rates and slower
  like-for-like resolution. The room configuration lives in a separate
  inventory file (classrooms.csv), so surfacing this requires a join.

Outputs:
  data/av_tickets.csv   - raw ticket export (scheduling noise included)
  data/classrooms.csv   - room inventory (config variant, equipment, refresh)

Usage:
  python scripts/generate_data.py --preview     # schema + distributions, no files written
  python scripts/generate_data.py               # write both CSVs
"""

import argparse
import csv
import math
import random
from datetime import datetime, timedelta

SEED = 42
N_HUMAN_TARGET = 530          # human-submitted AV tickets over the window
SCHED_RATIO = 3.4             # scheduling-automation rows per human ticket
START_DATE = datetime(2025, 1, 5)
END_DATE = datetime(2026, 6, 30)
TICKETS_PATH = "data/av_tickets.csv"
CLASSROOMS_PATH = "data/classrooms.csv"

# ---------------------------------------------------------------------------
# Classroom profiles — one building (fictional room numbers)
# ---------------------------------------------------------------------------
# config_variant drives the planted pattern; utilization reflects the heavy
# concentration seen in real data (a handful of core rooms carry most volume).

REFRESH_DATES = {
    "legacy_matrix_v1": "2017-08-20",
    "nvx_early": "2021-08-18",
    "nvx_standard": "2023-08-15",
}

CLASSROOMS = [
    # (classroom_id, floor, seats, config_variant, utilization, equipment)
    ("WIE-142", 1, 70, "legacy_matrix_v1", 2.6, "projector;hdmi_matrix;crestron_mpc;wireless_mic;capture_appliance"),
    ("WIE-251", 2, 64, "legacy_matrix_v1", 2.3, "projector;hdmi_matrix;crestron_mpc;wireless_mic;capture_appliance"),
    ("WIE-343", 3, 58, "legacy_matrix_v1", 2.1, "projector;hdmi_matrix;crestron_mpc;wireless_mic;capture_appliance"),
    ("WIE-355", 3, 58, "legacy_matrix_v1", 2.0, "projector;hdmi_matrix;crestron_mpc;wireless_mic"),
    ("WIE-312", 3, 48, "legacy_matrix_v1", 1.5, "projector;hdmi_matrix;crestron_mpc;wireless_mic"),
    ("WIE-105", 1, 85, "nvx_standard", 2.4, "dual_projector;nvx_encoder;crestron_ts;wireless_mic;ptz_camera;capture_appliance"),
    ("WIE-110", 1, 85, "nvx_standard", 2.2, "dual_projector;nvx_encoder;crestron_ts;wireless_mic;ptz_camera;capture_appliance"),
    ("WIE-148", 1, 60, "nvx_standard", 1.4, "projector;nvx_encoder;crestron_ts;wireless_mic;ptz_camera;capture_appliance"),
    ("WIE-205", 2, 60, "nvx_standard", 1.3, "projector;nvx_encoder;crestron_ts;wireless_mic;ptz_camera;capture_appliance"),
    ("WIE-246", 2, 55, "nvx_early", 1.2, "projector;nvx_encoder;crestron_ts;wireless_mic;capture_appliance"),
    ("WIE-258", 2, 55, "nvx_early", 1.1, "projector;nvx_encoder;crestron_ts;wireless_mic;capture_appliance"),
    ("WIE-306", 3, 48, "nvx_standard", 1.0, "projector;nvx_encoder;crestron_ts;wireless_mic;capture_appliance"),
    ("WIE-318", 3, 48, "nvx_standard", 0.9, "projector;nvx_encoder;crestron_ts;wireless_mic"),
    ("WIE-352", 3, 44, "nvx_early", 0.8, "projector;nvx_encoder;crestron_ts;wireless_mic;capture_appliance"),
    ("WIE-404", 4, 40, "nvx_standard", 0.7, "projector;nvx_encoder;crestron_ts;table_mic;capture_appliance"),
    ("WIE-412", 4, 40, "nvx_standard", 0.65, "projector;nvx_encoder;crestron_ts;table_mic"),
    ("WIE-441", 4, 36, "nvx_standard", 0.6, "display_85in;nvx_encoder;crestron_ts;table_mic"),
    ("WIE-455", 4, 36, "nvx_early", 0.55, "display_85in;nvx_encoder;crestron_ts;table_mic"),
    ("WIE-508", 5, 30, "nvx_standard", 0.5, "display_85in;nvx_encoder;crestron_ts;table_mic"),
    ("WIE-521", 5, 30, "nvx_standard", 0.45, "display_85in;nvx_encoder;crestron_ts;table_mic"),
    ("WIE-537", 5, 24, "nvx_standard", 0.4, "display_85in;nvx_encoder;crestron_ts;table_mic"),
    ("WIE-544", 5, 24, "nvx_standard", 0.35, "display_85in;nvx_encoder;crestron_ts;table_mic"),
]

BUILDING = "Wieboldt Hall"

# ---------------------------------------------------------------------------
# Issue catalog
# ---------------------------------------------------------------------------
# category -> mirrors a real higher-ed service taxonomy; subcategory carries
# the analytical detail. Weights are calibrated to the real issue mix
# (lecture capture is the single largest bucket; control-system issues rare).
# res_median is CALENDAR minutes (queue time included), lognormal spread.

ISSUES = [
    {
        "category": "AV Technical Support",
        "subcategory": "No display / HDMI handshake",
        "repeat_p": 0.39,
        "weight": 5,
        "res_median": 110, "res_spread": 2.3,
        "descriptions": [
            "Instructor laptop connected via HDMI but projector shows 'No Signal'.",
            "Podium PC displays on confidence monitor but projector screen is black.",
            "HDMI handshake failure after switching from podium PC to laptop.",
            "Projector shows brief image then drops to black screen repeatedly.",
            "Guest speaker laptop not detected on wall plate HDMI input.",
        ],
        "resolutions": [
            "Power-cycled matrix switcher and re-seated HDMI at podium; signal restored.",
            "Manually forced input on switcher; EDID re-handshake resolved the black screen.",
            "Replaced worn HDMI cable at podium wall plate.",
            "Rebooted control processor; input routing restored after reload.",
        ],
    },
    {
        "category": "AV Technical Support",
        "subcategory": "Input switching failure",
        "repeat_p": 0.36,
        "weight": 2.5,
        "res_median": 120, "res_spread": 2.3,
        "descriptions": [
            "Touch panel input selection not changing projector source.",
            "Room stuck on document camera input; cannot switch back to podium PC.",
            "Instructor unable to switch between laptop and PC mid-class.",
        ],
        "resolutions": [
            "Reloaded control program; input switching functional.",
            "Matrix switcher front-panel override cleared; touch panel control restored.",
            "Walked instructor through manual input selection; scheduled switcher config review.",
        ],
    },
    {
        "category": "AV Technical Support",
        "subcategory": "Audio / microphone",
        "repeat_p": 0.28,
        "weight": 8,
        "res_median": 220, "res_spread": 2.6,
        "descriptions": [
            "Lavalier mic cutting out intermittently during lecture.",
            "Laptop audio not playing through room speakers.",
            "Wireless mic static and dropouts near front of room.",
            "Program audio works but mic audio not reinforced in room.",
        ],
        "resolutions": [
            "Replaced batteries in bodypack; instructed on charging dock use.",
            "Corrected audio routing on touch panel; laptop audio restored.",
            "Swapped faulty bodypack transmitter with spare unit.",
            "Reset DSP to default preset; room audio normal.",
        ],
    },
    {
        "category": "AV Technical Support",
        "subcategory": "Control system / touch panel",
        "repeat_p": 0.35,
        "weight": 2,
        "res_median": 520, "res_spread": 2.4,
        "descriptions": [
            "Touch panel frozen on splash screen; no room control available.",
            "Control panel unresponsive to touch, backlight on.",
            "'System Starting' hangs indefinitely; room unusable for class.",
        ],
        "resolutions": [
            "Hard-reset touch panel via PoE port; control restored.",
            "Rebooted control processor; panel reconnected after program reload.",
            "Replaced failed relay module controlling projector power.",
        ],
    },
    {
        "category": "AV Technical Support",
        "subcategory": "Podium PC / login",
        "repeat_p": 0.21,
        "weight": 5,
        "res_median": 640, "res_spread": 2.4,
        "descriptions": [
            "Podium PC stuck on Windows update at class start.",
            "Instructor cannot log in to podium PC with NetID.",
            "Podium PC extremely slow to load PowerPoint.",
        ],
        "resolutions": [
            "Deferred updates to maintenance window; PC available for class.",
            "Re-joined machine to domain; login verified.",
            "Cleared temp files and restarted; escalated for RAM upgrade.",
        ],
    },
    {
        "category": "Lecture Capture",
        "subcategory": "Recording failed / not captured",
        "repeat_p": 0.49,
        "weight": 13,
        "res_median": 1900, "res_spread": 2.4,
        "descriptions": [
            "Scheduled class recording did not start; instructor reports no video in portal.",
            "Lecture recording missing audio track for full session.",
            "Recording stopped 20 minutes into class; remainder not captured.",
            "Capture appliance offline; last three scheduled recordings missing.",
        ],
        "resolutions": [
            "Restarted capture appliance; verified next scheduled recording completed.",
            "Recovered local backup recording and uploaded to course folder.",
            "Corrected room calendar mapping in capture scheduler.",
            "Re-seated audio feed to appliance; levels verified on test recording.",
        ],
    },
    {
        "category": "Lecture Capture",
        "subcategory": "Capture scheduling / setup",
        "repeat_p": 0.14,
        "weight": 8,
        "res_median": 4200, "res_spread": 2.2,
        "descriptions": [
            "Instructor requests recurring recording schedule for spring course.",
            "One-time recording request for guest lecture.",
            "Course recordings publishing to wrong folder; permissions need correction.",
        ],
        "resolutions": [
            "Created recurring capture schedule; confirmed first recording with instructor.",
            "Scheduled one-time recording; verified folder permissions.",
            "Re-mapped publishing folder and corrected course role permissions.",
        ],
    },
    {
        "category": "Webconferencing",
        "subcategory": "Zoom/Teams AV routing",
        "repeat_p": 0.25,
        "weight": 6,
        "res_median": 260, "res_spread": 2.6,
        "descriptions": [
            "Remote participants cannot hear in-room audio on Zoom call.",
            "Camera feed not appearing in Teams; shows black tile.",
            "Hybrid class: in-room students cannot hear remote participants.",
            "Zoom shows wrong camera; instructor blocked at class start.",
        ],
        "resolutions": [
            "Selected correct USB bridge as mic/speaker in Zoom; verified with test call.",
            "Re-seated USB extender at podium; camera re-enumerated in Teams.",
            "Set camera preset and saved default; walked instructor through controls.",
        ],
    },
    {
        "category": "Webconferencing",
        "subcategory": "Camera / PTZ",
        "repeat_p": 0.28,
        "weight": 2.5,
        "res_median": 3000, "res_spread": 2.4,
        "descriptions": [
            "PTZ camera not responding to touch panel presets.",
            "Auto-tracking camera losing instructor near whiteboard.",
            "Camera image degraded; colors washed out on far end.",
        ],
        "resolutions": [
            "Restored camera presets from backup; tracking verified.",
            "Recalibrated auto-tracking zones; verified during live class.",
            "Replaced camera; presets rebuilt and tested.",
        ],
    },
    {
        "category": "Equipment Maintenance & Repair",
        "subcategory": "Projector lamp / image quality",
        "repeat_p": 0.21,
        "weight": 3,
        "res_median": 7500, "res_spread": 2.4,
        "descriptions": [
            "Projector image noticeably dim, colors washed out.",
            "Projector filter warning on startup, image flickering.",
            "Yellow tint on projected image, worse on left side.",
        ],
        "resolutions": [
            "Replaced projector lamp; brightness restored.",
            "Cleaned filter and reset lamp hours counter.",
            "Scheduled projector replacement; loaner cart provided in interim.",
        ],
    },
    {
        "category": "Equipment Maintenance & Repair",
        "subcategory": "Cabling / connectors",
        "repeat_p": 0.14,
        "weight": 2,
        "res_median": 5200, "res_spread": 2.4,
        "descriptions": [
            "USB-C adapter at podium missing; instructor cannot connect MacBook.",
            "HDMI cable at podium has bent pin, intermittent connection.",
            "Wall plate faceplate loose, cable strain on connector.",
        ],
        "resolutions": [
            "Replaced missing adapter; added to weekly checklist.",
            "Swapped damaged HDMI cable; tested with laptop.",
            "Re-secured wall plate and tested all inputs.",
        ],
    },
    {
        "category": "Equipment Maintenance & Repair",
        "subcategory": "Preventative maintenance",
        "repeat_p": 0.03,
        "weight": 4,
        "res_median": 9500, "res_spread": 2.0,
        "descriptions": [
            "Quarterly AV preventative maintenance check.",
            "Firmware update window for control devices.",
            "Semester-start room readiness verification.",
        ],
        "resolutions": [
            "Completed PM checklist; all systems nominal.",
            "Updated device firmware; verified control and AV paths.",
            "Room verified ready; minor cable management performed.",
        ],
    },
    {
        "category": "Setup & Configuration",
        "subcategory": "Event / class AV setup",
        "repeat_p": 0.07,
        "weight": 6,
        "res_median": 6000, "res_spread": 2.2,
        "descriptions": [
            "AV setup requested for admissions information session.",
            "Microphone and projector setup for guest speaker event.",
            "Panel discussion: three handhelds and confidence monitor requested.",
        ],
        "resolutions": [
            "Completed setup and tested with event organizer.",
            "Provided requested microphones; staffed first 15 minutes of event.",
            "Configured room for panel format; struck equipment after event.",
        ],
    },
    {
        "category": "Consultation",
        "subcategory": "AV consultation / training",
        "repeat_p": 0.04,
        "weight": 4,
        "res_median": 7200, "res_spread": 2.2,
        "descriptions": [
            "New faculty member requests walkthrough of classroom AV system.",
            "Department asks for guidance on recording equipment for workshop series.",
            "Instructor requests best-practice review for hybrid teaching setup.",
        ],
        "resolutions": [
            "Provided 30-minute room orientation; left quick-reference guide.",
            "Recommended equipment configuration; scheduled follow-up.",
            "Reviewed hybrid workflow and set camera/audio defaults with instructor.",
        ],
    },
]

# Multipliers applied to issue weights per config variant (the planted pattern).
CONFIG_MULTIPLIERS = {
    "legacy_matrix_v1": {
        "No display / HDMI handshake": 2.9,
        "Input switching failure": 2.6,
        "Control system / touch panel": 1.5,
    },
    "nvx_early": {
        "Zoom/Teams AV routing": 1.4,
        "Recording failed / not captured": 1.3,
    },
    "nvx_standard": {},
}

# Ten technicians; top-3 carry ~70% of assignments (calibrated concentration).
TECHNICIANS = [
    ("A. Okafor", 18), ("M. Reyes", 16), ("D. Lindqvist", 14),
    ("S. Patel", 8), ("J. Whitfield", 6), ("T. Nakamura", 5),
    ("R. Calloway", 4), ("E. Marsh", 3), ("K. Duval", 3), ("L. Ferreira", 3),
]

# Fictional course inventory for scheduling-automation rows.
SCHED_TITLES = [
    "FINC-430-0-51 Corporate Finance", "MKTG-450-0-61 Brand Strategy",
    "MECN-425-0-52 Managerial Economics", "STRT-452-0-71 Competitive Strategy",
    "ACCT-410-0-51 Financial Accounting", "OPNS-430-0-62 Operations Management",
    "MORS-470-0-51 Negotiations", "DECS-433-0-61 Business Analytics",
    "Leadership Coaching Session", "Admissions Information Session",
    "Executive Education Workshop", "Student Club Panel Event",
    "Faculty Meeting", "Room Hold — Facilities",
]

# ---------------------------------------------------------------------------
# Calendar profiles (calibrated to real aggregate shapes)
# ---------------------------------------------------------------------------

# Relative volume by month: spring-quarter peak, deep summer & December troughs.
MONTH_WEIGHTS = {1: 45, 2: 26, 3: 40, 4: 60, 5: 50, 6: 40,
                 7: 10, 8: 9, 9: 29, 10: 41, 11: 31, 12: 11}
YEAR_GROWTH = {2025: 1.0, 2026: 1.18}   # modest year-over-year volume growth

# Tue/Wed/Thu heaviest; real weekend teaching means Saturday volume exists.
DOW_WEIGHTS = [1.0, 1.9, 1.6, 1.4, 0.95, 0.75, 0.32]   # Mon..Sun

# Broad mid-day peak with an evening-program tail (hours 7..22).
HOURS = list(range(7, 23))
HOUR_WEIGHTS = [7, 25, 51, 84, 75, 67, 52, 70, 56, 52, 50, 30, 21, 20, 16, 3]
# Legacy-room display issues cluster at first use of the day (morning + early evening).
HOUR_WEIGHTS_COLDSTART = [10, 60, 70, 45, 30, 30, 30, 35, 25, 25, 30, 45, 20, 12, 8, 2]


def day_weight(d: datetime) -> float:
    return MONTH_WEIGHTS[d.month] * YEAR_GROWTH[d.year] * DOW_WEIGHTS[d.weekday()]


def lognormal_minutes(rng: random.Random, median: float, spread: float) -> int:
    val = math.exp(math.log(median) + rng.gauss(0, spread))
    return max(2, int(round(val)))


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def build_date_pool():
    dates, weights = [], []
    d = START_DATE
    while d <= END_DATE:
        dates.append(d)
        weights.append(day_weight(d))
        d += timedelta(days=1)
    return dates, weights


def generate(n_human: int, seed: int):
    rng = random.Random(seed)
    dates, date_weights = build_date_pool()

    room_issue_weights = {}
    for cid, _fl, _seats, config, _util, equipment in CLASSROOMS:
        ws = []
        for issue in ISSUES:
            w = issue["weight"]
            w *= CONFIG_MULTIPLIERS[config].get(issue["subcategory"], 1.0)
            if "capture" in issue["subcategory"].lower() or issue["category"] == "Lecture Capture":
                if "capture_appliance" not in equipment:
                    w *= 0.15   # rooms without appliances rarely file capture tickets
            if issue["subcategory"] == "Camera / PTZ" and "ptz_camera" not in equipment:
                w *= 0.25
            ws.append(w)
        room_issue_weights[cid] = ws

    room_weights = []
    for _cid, _fl, _seats, config, util, _eq in CLASSROOMS:
        penalty = {"legacy_matrix_v1": 1.5, "nvx_early": 1.15, "nvx_standard": 1.0}[config]
        room_weights.append(util * penalty)

    tech_names = [t[0] for t in TECHNICIANS]
    tech_wts = [t[1] for t in TECHNICIANS]

    def requester_id():
        # Role-prefixed synthetic requester IDs ("Faculty4521067"), deliberately
        # NOT NetID-shaped so no generated value can collide with a real
        # institutional identifier. Draws the same number of values from the
        # shared RNG as earlier versions, keeping the rest of the dataset
        # reproducible under the fixed seed.
        a = rng.choice("abcdefghijklmnopqrstuvwxyz")
        b = rng.choice("abcdefghijklmnopqrstuvwxyz")
        c = rng.choice("abcdefghijklmnopqrstuvwxyz")
        n = rng.randrange(100, 9999)
        role = "Faculty" if a <= "m" else ("Staff" if a <= "t" else "Student")
        return f"{role}{n}{(ord(b) - 97) * 26 + (ord(c) - 97):03d}"

    rows = []
    ticket_num = 200001

    # --- Human AV support tickets -----------------------------------------
    for _ in range(n_human):
        room = rng.choices(CLASSROOMS, weights=room_weights)[0]
        cid, _fl, _seats, config, _util, _eq = room
        issue = rng.choices(ISSUES, weights=room_issue_weights[cid])[0]

        day = rng.choices(dates, weights=date_weights)[0]
        cold = (config == "legacy_matrix_v1" and issue["subcategory"] in
                ("No display / HDMI handshake", "Input switching failure"))
        hour_w = HOUR_WEIGHTS_COLDSTART if cold else HOUR_WEIGHTS
        hour = rng.choices(HOURS, weights=hour_w)[0]
        created = day.replace(hour=hour, minute=rng.randrange(60))

        tech = rng.choices(tech_names, weights=tech_wts)[0]
        minutes = lognormal_minutes(rng, issue["res_median"], issue["res_spread"])
        if cold:
            minutes = int(minutes * rng.uniform(1.3, 1.7))   # slower like-for-like fixes

        resolved = created + timedelta(minutes=minutes)
        is_open = rng.random() < 0.03 or resolved > END_DATE + timedelta(days=15)
        if is_open:
            resolved, minutes = None, None
        resolution = rng.choice(issue["resolutions"]) if not is_open else ""

        # ~30% of human tickets arrive with no room attribution (building only)
        room_out = "" if rng.random() < 0.30 else cid
        if room_out and rng.random() < 0.02:
            room_out += " "                                   # whitespace mess

        category = issue["category"]
        r = rng.random()
        if r < 0.015:
            category = category.upper()
        elif r < 0.03:
            category = category.lower()

        rows.append({
            "ticket_id": f"INC{ticket_num:07d}",
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S"),
            "resolved_at": resolved.strftime("%Y-%m-%d %H:%M:%S") if resolved else "",
            "created_by": requester_id(),
            "classroom_id": room_out,
            "building": BUILDING,
            "category": category,
            "subcategory": issue["subcategory"],
            "description": rng.choice(issue["descriptions"]),
            "resolution_notes": resolution,
            "assigned_technician": tech,
            "resolution_time_minutes": minutes if minutes is not None else "",
            "_room_true": cid,
        })
        ticket_num += 1

        # Recurrence chains: unresolved root causes generate follow-up tickets
        # in the same room within days (calibrated to the real repeat-rate baseline).
        rp = issue.get("repeat_p", 0.1)
        if cold:
            rp = min(0.68, rp * 2.0)   # legacy config: symptom fixed, cause remains
        chain_created = created
        while rng.random() < rp:
            chain_created = chain_created + timedelta(
                days=rng.randrange(1, 14), hours=rng.randrange(-3, 4))
            if chain_created > END_DATE.replace(hour=20):
                break
            hour2 = rng.choices(HOURS, weights=hour_w)[0]
            chain_created = chain_created.replace(hour=hour2, minute=rng.randrange(60))
            minutes2 = lognormal_minutes(rng, issue["res_median"], issue["res_spread"])
            if cold:
                minutes2 = int(minutes2 * rng.uniform(1.3, 1.7))
            resolved2 = chain_created + timedelta(minutes=minutes2)
            open2 = rng.random() < 0.03 or resolved2 > END_DATE + timedelta(days=15)
            room_out2 = "" if rng.random() < 0.18 else cid   # repeats get rooms more often
            rows.append({
                "ticket_id": f"INC{ticket_num:07d}",
                "created_at": chain_created.strftime("%Y-%m-%d %H:%M:%S"),
                "resolved_at": "" if open2 else resolved2.strftime("%Y-%m-%d %H:%M:%S"),
                "created_by": requester_id(),
                "classroom_id": room_out2,
                "building": BUILDING,
                "category": issue["category"],
                "subcategory": issue["subcategory"],
                "description": rng.choice(issue["descriptions"]),
                "resolution_notes": "" if open2 else rng.choice(issue["resolutions"]),
                "assigned_technician": rng.choices(tech_names, weights=tech_wts)[0],
                "resolution_time_minutes": "" if open2 else minutes2,
                "_room_true": cid,
            })
            ticket_num += 1
            rp *= 0.55

        # ~1.5% double-submitted duplicates
        if rng.random() < 0.025:
            dup = dict(rows[-1])
            dup["ticket_id"] = f"INC{ticket_num:07d}"
            dup_created = created + timedelta(minutes=rng.randrange(2, 9))
            dup["created_at"] = dup_created.strftime("%Y-%m-%d %H:%M:%S")
            dup["resolution_notes"] = "Duplicate of earlier ticket; closed."
            dup["resolution_time_minutes"] = rng.randrange(3, 30)
            if dup["resolved_at"]:
                dup["resolved_at"] = (dup_created + timedelta(
                    minutes=int(dup["resolution_time_minutes"]))).strftime("%Y-%m-%d %H:%M:%S")
            rows.append(dup)
            ticket_num += 1

    # --- Scheduling-automation rows (25Live integration noise) -------------
    n_sched = int(n_human * SCHED_RATIO)
    for _ in range(n_sched):
        room = rng.choices(CLASSROOMS, weights=room_weights)[0]
        day = rng.choices(dates, weights=date_weights)[0]
        created = day.replace(hour=rng.choices([5, 6, 7], weights=[5, 3, 2])[0],
                              minute=rng.randrange(60), second=rng.randrange(60))
        resolved = created + timedelta(minutes=rng.randrange(1, 30))
        auto_open = rng.random() < 0.15
        rows.append({
            "ticket_id": f"INC{ticket_num:07d}",
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S"),
            "resolved_at": "" if auto_open else resolved.strftime("%Y-%m-%d %H:%M:%S"),
            "created_by": "25Live",
            "classroom_id": room[0],
            "building": BUILDING,
            "category": "Classroom Scheduling",
            "subcategory": "Room reservation sync",
            "description": rng.choice(SCHED_TITLES),
            "resolution_notes": "" if auto_open else "Auto-closed by scheduling integration.",
            "assigned_technician": "",
            "resolution_time_minutes": "" if auto_open else rng.randrange(1, 30),
            "_room_true": room[0],
        })
        ticket_num += 1

    rows.sort(key=lambda r: r["created_at"])
    return rows


TICKET_FIELDS = [
    "ticket_id", "created_at", "resolved_at", "created_by", "classroom_id",
    "building", "category", "subcategory", "description", "resolution_notes",
    "assigned_technician", "resolution_time_minutes",
]

CLASSROOM_FIELDS = [
    "classroom_id", "building", "floor", "seats", "config_variant", "equipment",
    "last_av_refresh",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true",
                        help="Print schema and distributions without writing CSVs")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--n", type=int, default=N_HUMAN_TARGET)
    args = parser.parse_args()

    rows = generate(args.n, args.seed)
    human = [r for r in rows if r["created_by"] != "25Live"]

    if args.preview:
        from collections import Counter
        print(f"Generated {len(rows)} raw rows ({len(human)} human, "
              f"{len(rows) - len(human)} scheduling-automation)\n")
        print("Ticket schema:", ", ".join(TICKET_FIELDS))
        print("Classroom schema:", ", ".join(CLASSROOM_FIELDS), "\n")
        by_month = Counter(r["created_at"][:7] for r in human)
        print("Human tickets by month:")
        for m in sorted(by_month):
            print(f"  {m}: {by_month[m]}")
        print("\nHuman tickets by subcategory:")
        for sub, n in Counter(r["subcategory"] for r in human).most_common():
            print(f"  {sub}: {n}")
        by_room = Counter(r["_room_true"] for r in human)
        print("\nTop 8 rooms (true attribution):")
        for room, n in by_room.most_common(8):
            print(f"  {room}: {n}")
        missing = sum(1 for r in human if not r["classroom_id"].strip())
        openn = sum(1 for r in human if not r["resolved_at"])
        res = sorted(int(r["resolution_time_minutes"]) for r in human
                     if r["resolution_time_minutes"] != "")
        def pct(p): return res[int(p * len(res))]
        print(f"\nMissing room: {missing/len(human):.0%} | open: {openn/len(human):.0%}")
        print(f"Resolution minutes p25/p50/p75/p90: "
              f"{pct(.25)} / {pct(.5)} / {pct(.75)} / {pct(.9)}")
        print(f"Share <1h: {sum(1 for m in res if m < 60)/len(res):.0%} | "
              f">24h: {sum(1 for m in res if m > 1440)/len(res):.0%}")
        return

    with open(TICKETS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TICKET_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows ({len(human)} human) to {TICKETS_PATH}")

    with open(CLASSROOMS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CLASSROOM_FIELDS)
        writer.writeheader()
        for cid, floor, seats, config, _util, equipment in CLASSROOMS:
            writer.writerow({
                "classroom_id": cid,
                "building": BUILDING,
                "floor": floor,
                "seats": seats,
                "config_variant": config,
                "equipment": equipment,
                "last_av_refresh": REFRESH_DATES[config],
            })
    print(f"Wrote {len(CLASSROOMS)} rooms to {CLASSROOMS_PATH}")


if __name__ == "__main__":
    main()
