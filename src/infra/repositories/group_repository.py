import json
import uuid
from datetime import datetime, date
from typing import Optional

from ...domain.models import Group, Member, GroupPreferences
from ...domain.enums import ProfileType
from ..database.connection import get_connection


class GroupRepository:

    def get_by_phone(self, whatsapp_number: str) -> Optional[Group]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM groups WHERE whatsapp_number = ?", (whatsapp_number,)
            ).fetchone()
            if not row:
                return None
            return self._hydrate_group(conn, dict(row))

    def get_by_id(self, group_id: str) -> Optional[Group]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if not row:
                return None
            return self._hydrate_group(conn, dict(row))

    def create(self, whatsapp_number: str, park_id: str, visit_date: date, language: str = "pt-BR") -> Group:
        group_id = f"grp_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO groups (group_id, whatsapp_number, park_id, visit_date, language, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (group_id, whatsapp_number, park_id, visit_date.isoformat(), language, now),
            )
        return Group(
            group_id=group_id,
            whatsapp_number=whatsapp_number,
            park_id=park_id,
            visit_date=visit_date,
            language=language,
            created_at=datetime.fromisoformat(now),
        )

    def update_members(self, group_id: str, members: list[Member]) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM members WHERE group_id = ?", (group_id,))
            for member in members:
                conn.execute(
                    """INSERT INTO members
                       (member_id, group_id, role, age, height_cm, name,
                        fear_of_dark, fear_of_heights, motion_sickness, mobility_restricted)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid.uuid4().hex, group_id, member.role, member.age,
                        member.height_cm, member.name,
                        int(member.fear_of_dark), int(member.fear_of_heights),
                        int(member.motion_sickness), int(member.mobility_restricted),
                    ),
                )

    def update_profile(self, group_id: str, profile_id: ProfileType, setup_complete: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE groups SET profile_id = ?, setup_complete = ? WHERE group_id = ?",
                (profile_id.value, int(setup_complete), group_id),
            )

    def save_preferences(self, prefs: GroupPreferences) -> None:
        pref_id = f"pref_{uuid.uuid4().hex[:10]}"
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO group_preferences
                   (pref_id, group_id, intensity_preference, priority_order, avoid_types,
                    max_queue_minutes, must_do_attractions, skip_attractions,
                    show_interest, meal_break_times, allow_group_split, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(group_id) DO UPDATE SET
                     intensity_preference=excluded.intensity_preference,
                     priority_order=excluded.priority_order,
                     avoid_types=excluded.avoid_types,
                     max_queue_minutes=excluded.max_queue_minutes,
                     must_do_attractions=excluded.must_do_attractions,
                     skip_attractions=excluded.skip_attractions,
                     show_interest=excluded.show_interest,
                     meal_break_times=excluded.meal_break_times,
                     allow_group_split=excluded.allow_group_split,
                     updated_at=excluded.updated_at""",
                (
                    pref_id, prefs.group_id, prefs.intensity_preference,
                    json.dumps(prefs.priority_order), json.dumps(prefs.avoid_types),
                    prefs.max_queue_minutes, json.dumps(prefs.must_do_attractions),
                    json.dumps(prefs.skip_attractions), int(prefs.show_interest),
                    json.dumps(prefs.meal_break_times), int(prefs.allow_group_split), now,
                ),
            )

    def get_preferences(self, group_id: str) -> Optional[GroupPreferences]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM group_preferences WHERE group_id = ?", (group_id,)
            ).fetchone()
            if not row:
                return None
            r = dict(row)
            return GroupPreferences(
                pref_id=r["pref_id"],
                group_id=r["group_id"],
                intensity_preference=r["intensity_preference"],
                priority_order=json.loads(r["priority_order"]),
                avoid_types=json.loads(r["avoid_types"]),
                max_queue_minutes=r["max_queue_minutes"],
                must_do_attractions=json.loads(r["must_do_attractions"]),
                skip_attractions=json.loads(r["skip_attractions"]),
                show_interest=bool(r["show_interest"]),
                meal_break_times=json.loads(r["meal_break_times"]),
                allow_group_split=bool(r["allow_group_split"]),
            )

    def _hydrate_group(self, conn: object, row: dict) -> Group:
        members_rows = conn.execute(
            "SELECT * FROM members WHERE group_id = ?", (row["group_id"],)
        ).fetchall()
        members = [
            Member(
                role=m["role"], age=m["age"], height_cm=m["height_cm"],
                name=m["name"], fear_of_dark=bool(m["fear_of_dark"]),
                fear_of_heights=bool(m["fear_of_heights"]),
                motion_sickness=bool(m["motion_sickness"]),
                mobility_restricted=bool(m["mobility_restricted"]),
            )
            for m in members_rows
        ]
        return Group(
            group_id=row["group_id"],
            whatsapp_number=row["whatsapp_number"],
            park_id=row["park_id"],
            visit_date=date.fromisoformat(row["visit_date"]),
            language=row["language"],
            profile_id=ProfileType(row["profile_id"]) if row["profile_id"] else None,
            setup_complete=bool(row["setup_complete"]),
            members=members,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )


def get_group_repository() -> GroupRepository:
    return GroupRepository()
