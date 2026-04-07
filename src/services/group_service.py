import uuid
from datetime import date, datetime
from typing import Optional

from ..domain.models import Group, Member, GroupPreferences
from ..domain.enums import ProfileType
from ..domain.exceptions.domain_exceptions import GroupNotFound, GroupSetupIncomplete
from ..decision.profile_detector import detect_profile
from ..infra.repositories.group_repository import get_group_repository


class GroupService:

    def __init__(self):
        self._repo = get_group_repository()

    def get_or_create(
        self,
        whatsapp_number: str,
        park_id: str = "magic_kingdom",
        visit_date: Optional[date] = None,
    ) -> tuple[Group, bool]:
        """Retorna (grupo, created). created=True se foi criado agora.
        Se park_id foi informado e é diferente do existente, atualiza."""
        existing = self._repo.get_by_phone(whatsapp_number)
        if existing:
            # Atualiza park_id se veio diferente (cliente trocou de parque pelo app)
            if park_id and park_id != "magic_kingdom" and existing.park_id != park_id:
                self._repo.update_park(existing.group_id, park_id)
                existing.park_id = park_id
            return existing, False

        group = self._repo.create(
            whatsapp_number=whatsapp_number,
            park_id=park_id,
            visit_date=visit_date or date.today(),
        )
        return group, True

    def get_by_id(self, group_id: str) -> Group:
        group = self._repo.get_by_id(group_id)
        if not group:
            raise GroupNotFound(group_id)
        return group

    def update_members(self, group_id: str, members: list[Member]) -> Group:
        group = self.get_by_id(group_id)
        self._repo.update_members(group_id, members)

        # Detecta perfil automaticamente após atualizar membros
        profile = detect_profile(members)
        has_prefs = self._repo.get_preferences(group_id) is not None
        self._repo.update_profile(group_id, profile, setup_complete=has_prefs)

        group.members = members
        group.profile_id = profile
        return group

    def save_preferences(self, group_id: str, preferences: GroupPreferences) -> Group:
        group = self.get_by_id(group_id)
        self._repo.save_preferences(preferences)

        has_members = len(group.members) > 0
        self._repo.update_profile(group_id, group.profile_id or ProfileType.P4, setup_complete=has_members)

        group.setup_complete = has_members
        return group

    def get_preferences(self, group_id: str) -> Optional[GroupPreferences]:
        return self._repo.get_preferences(group_id)

    def assert_setup_complete(self, group: Group) -> None:
        if not group.setup_complete:
            next_step = "add_members" if not group.members else "add_preferences"
            raise GroupSetupIncomplete(group.group_id, next_step)
