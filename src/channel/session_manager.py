"""
session_manager.py — Mapeia número de telefone para group_id.

MVP: cache em memória (dict). Sobrevive enquanto o processo viver.
Produção: substituir por Redis com TTL de 24h.

INTERFACE pública:
    resolve(phone) -> Optional[str]   — busca group_id pelo telefone
    register(phone, group_id)         — associa após criação de grupo
    invalidate(phone)                 — limpa ao resetar sessão
    get_session_context(phone)        — retorna dict com metadados da sessão
    update_session_context(phone, **kwargs) — atualiza metadados
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """
    Dados de sessão mantidos por telefone.
    Contém o group_id e metadados do estado da conversa.
    """
    group_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Contexto útil para enriquecer o NLU sem precisar de banco
    last_known_location: Optional[str] = None   # última área reportada
    last_intent: Optional[str] = None           # último intent processado
    message_count: int = 0                      # mensagens nesta sessão


class SessionManager:
    """
    Gerencia sessões ativas por número de telefone.

    Fronteira clara: SessionManager APENAS mantém o mapeamento
    phone → group_id + contexto leve. Não acessa lógica de domínio.
    """

    def __init__(self):
        self._sessions: dict[str, SessionData] = {}

    def resolve(self, phone: str) -> Optional[str]:
        """
        Retorna group_id mais recente. Sempre consulta banco para pegar
        o grupo mais novo (caso cliente reconfigure pelo app).
        """
        # Sempre busca o mais recente no banco
        group_id = self._lookup_from_db(phone)
        if group_id:
            # Atualiza sessão em memória com o grupo mais recente
            if phone not in self._sessions or self._sessions[phone].group_id != group_id:
                self._sessions[phone] = SessionData(group_id=group_id)
                logger.debug("session_updated phone=%s group=%s", phone, group_id)
            else:
                self._sessions[phone].last_active = datetime.now(timezone.utc)
            return group_id

        return None

    def register(self, phone: str, group_id: str) -> None:
        """Associa um telefone a um group_id após criação ou login."""
        self._sessions[phone] = SessionData(group_id=group_id)
        logger.info("session_registered phone=%s group=%s", phone, group_id)

    def invalidate(self, phone: str) -> None:
        """Remove sessão — usado ao resetar o grupo ou por timeout."""
        self._sessions.pop(phone, None)

    def get_context(self, phone: str) -> dict:
        """
        Retorna contexto de sessão enriquecido para o NLU.
        Usado pelo message_router para construir session_context.
        """
        session = self._sessions.get(phone)
        if not session:
            return {}
        return {
            "last_location": session.last_known_location,
            "last_intent": session.last_intent,
            "message_count": session.message_count,
        }

    def update_context(self, phone: str, **kwargs) -> None:
        """Atualiza metadados da sessão após processar uma mensagem."""
        session = self._sessions.get(phone)
        if not session:
            return
        if "location" in kwargs:
            session.last_known_location = kwargs["location"]
        if "intent" in kwargs:
            session.last_intent = kwargs["intent"]
        session.message_count += 1
        session.last_active = datetime.now(timezone.utc)

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)

    def _lookup_from_db(self, phone: str) -> Optional[str]:
        """Busca o group_id mais recente no banco para este telefone."""
        try:
            from ..infra.database.connection import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT group_id FROM groups WHERE whatsapp_number = ? ORDER BY created_at DESC LIMIT 1",
                    (phone,)
                ).fetchone()
                return row["group_id"] if row else None
        except Exception as e:
            logger.warning("session_db_lookup_failed phone=%s error=%s", phone, e)
            return None


# Singleton por processo
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _session_manager
