"""
contracts.py — Contratos da fronteira canal ↔ motor.

REGRA DE ORO:
  Nada fora deste arquivo conhece Twilio, TwiML ou HTTP.
  Nada dentro do motor conhece canais, webhooks ou provedores.

  canal (whatsapp_handler) ─── InboundMessage ──► motor (message_router)
  motor (message_router)   ◄── OutboundMessage ─── canal (whatsapp_handler)

Para adicionar um novo canal (Telegram, Instagram, REST direto):
  1. Crie um novo *_handler.py que produz InboundMessage e consome OutboundMessage.
  2. Zero mudanças no motor.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    SMS      = "sms"       # futuro
    REST_API = "rest_api"  # para testes automatizados e dashboard


class MediaType(str, Enum):
    TEXT  = "text"
    IMAGE = "image"  # foto da fila, mapa, screenshot
    AUDIO = "audio"  # mensagem de voz (futuro)


class DeliveryStatus(str, Enum):
    """Estado de entrega da mensagem de saída — usado para rastreio."""
    QUEUED    = "queued"     # enfileirada para envio
    SENT      = "sent"       # aceita pelo provedor
    DELIVERED = "delivered"  # confirmada no dispositivo (callback Twilio)
    FAILED    = "failed"     # falha de entrega
    FALLBACK  = "fallback"   # resposta de emergência gerada por erro interno


# ─────────────────────────────────────────────────────────────────────────────
# EVENTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InboundMessage:
    """
    Mensagem recebida do usuário — normalizada, sem detalhes de canal.

    Produzida por: TwilioAdapter.parse()
    Consumida por: MessageRouter.route()

    Campos obrigatórios:
        phone       — identificador único do usuário (E.164)
        channel     — canal de origem
        raw_text    — texto bruto, sem modificação
        received_at — timestamp de recebimento

    Campos injetados pelo handler antes do roteamento:
        group_id    — resolvido pelo SessionManager
    """
    # Identidade
    phone:       str          # E.164: +5521999990000
    channel:     ChannelType
    raw_text:    str          # texto bruto, preservado para logging e NLU
    received_at: datetime

    # Metadados do provedor (opcionais — podem não vir em todos os canais)
    display_name:       str = ""    # nome do perfil WhatsApp (não confiável para auth)
    message_id:         str = ""    # MessageSid do Twilio, ID do Meta etc.
    media_url:          Optional[str] = None
    media_type:         MediaType = MediaType.TEXT

    # Injetado pelo handler — não vem do provedor
    group_id:           Optional[str] = None   # preenchido pelo SessionManager

    # ── Propriedades derivadas ────────────────────────────────────────────────

    @property
    def is_empty(self) -> bool:
        return not self.raw_text.strip()

    @property
    def is_media(self) -> bool:
        return self.media_type != MediaType.TEXT and self.media_url is not None

    @property
    def is_new_user(self) -> bool:
        """True se o grupo ainda não foi criado para este telefone."""
        return self.group_id is None

    @property
    def truncated_text(self) -> str:
        """Versão curta para logs — nunca loga texto completo em produção."""
        return self.raw_text[:60] + ("…" if len(self.raw_text) > 60 else "")


# ─────────────────────────────────────────────────────────────────────────────
# EVENTO DE SAÍDA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OutboundMessage:
    """
    Resposta a ser enviada ao usuário — pronta para o canal.

    Produzida por: MessageRouter.route()
    Consumida por: TwilioAdapter.render() ou Twilio Messaging API

    O campo `text` contém a mensagem final PT-BR, pronta para envio.
    O handler não altera o texto — apenas serializa para o formato do canal.

    Campos de controle (usados para rastreio e auditoria):
        recommendation_id — ID da Recommendation do domínio (para feedback loop)
        intent_handled    — intent NLU que gerou esta resposta
        delivery_status   — rastreio de entrega (atualizado via webhook de status)
    """
    # Destino
    to_phone: str
    channel:  ChannelType
    text:     str          # mensagem final PT-BR, pronta para envio

    # Rastreio
    generated_at:       datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recommendation_id:  Optional[str] = None  # liga a resposta à Recommendation do domínio
    intent_handled:     str = ""              # "GET_REC", "MARK_DONE" etc.
    confidence:         float = 1.0           # confiança do NLU (0–1)
    delivery_status:    DeliveryStatus = DeliveryStatus.QUEUED

    # Flags de qualidade — usados para análise e alertas
    used_llm:       bool = False  # se o LLM foi acionado (custo + latência)
    fallback_used:  bool = False  # se caiu no template de emergência
    needs_followup: bool = False  # se o sistema espera resposta imediata

    # ── Serialização para TwiML (resposta síncrona ao webhook) ───────────────

    def to_twiml(self) -> str:
        """
        Renderiza como TwiML para resposta síncrona ao webhook Twilio.

        Usado quando a mensagem é gerada dentro do timeout de 15s do Twilio.
        Para respostas mais lentas, usar a Twilio Messaging API de forma assíncrona.
        """
        safe = (self.text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            f"<Response><Message>{safe}</Message></Response>"
        )

    def to_empty_twiml(self) -> str:
        """
        TwiML vazio — usado quando a resposta será enviada via API assíncrona.
        O Twilio precisa de HTTP 200, mas não envia a mensagem pelo webhook.
        """
        return "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"

    # ── Propriedades derivadas ────────────────────────────────────────────────

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_long(self) -> bool:
        """Mensagens > 400 chars podem ser cortadas em algumas operadoras."""
        return self.char_count > 400

    def is_valid(self) -> bool:
        return bool(self.text.strip() and self.to_phone)


# ─────────────────────────────────────────────────────────────────────────────
# EVENTO DE STATUS DE ENTREGA (webhook de callback do Twilio)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DeliveryEvent:
    """
    Evento recebido no callback de status do Twilio.

    Twilio chama /webhook/whatsapp/status quando o status de uma mensagem
    enviada muda (queued → sent → delivered ou failed).

    Usado para:
      - Detectar falhas de entrega e retentar
      - Medir taxa de entrega por grupo/região
      - Disparar alertas operacionais
    """
    message_sid:  str           # MessageSid original
    to_phone:     str           # destinatário
    status:       str           # "queued" | "sent" | "delivered" | "failed" | "undelivered"
    error_code:   Optional[str] = None   # código de erro Twilio se falhou
    error_message: Optional[str] = None
    timestamp:    datetime = field(default_factory=lambda: datetime.now(timezone.utc))
