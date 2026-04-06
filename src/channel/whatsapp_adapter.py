"""
whatsapp_adapter.py — Adaptador Twilio ↔ contratos internos.

RESPONSABILIDADE ÚNICA:
  Traduzir Twilio form-data → InboundMessage
  Traduzir OutboundMessage → TwiML

TROCAR DE PROVEDOR:
  Substitua este arquivo por meta_adapter.py, messagebird_adapter.py etc.
  Nenhum outro arquivo muda. O contrato (InboundMessage/OutboundMessage) fica.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Optional

from .contracts import InboundMessage, OutboundMessage, ChannelType, MediaType
from ..config import settings

logger = logging.getLogger(__name__)


class TwilioAdapter:
    """
    Converte entre formato Twilio e contratos internos.
    Estado: nenhum. Thread-safe como singleton.
    """

    # ── Entrada: Twilio form-data → InboundMessage ────────────────────────────

    def parse(
        self,
        from_field: str,
        body: str,
        profile_name: str = "",
        message_sid: str = "",
        num_media: str = "0",
        media_url: Optional[str] = None,
        media_content_type: Optional[str] = None,
    ) -> InboundMessage:
        """
        Converte campos do POST do Twilio em InboundMessage normalizado.

        Twilio envia: Content-Type: application/x-www-form-urlencoded
        Campos: From, Body, ProfileName, MessageSid, NumMedia, MediaUrl0, MediaContentType0
        """
        # Normaliza número: remove prefixo "whatsapp:" que Twilio adiciona
        phone = from_field.replace("whatsapp:", "").strip()

        # Detecta tipo de mídia se houver anexo
        media_type = MediaType.TEXT
        if num_media and int(num_media) > 0:
            ct = (media_content_type or "").lower()
            if "image" in ct:
                media_type = MediaType.IMAGE
            elif "audio" in ct or "ogg" in ct:
                media_type = MediaType.AUDIO

        return InboundMessage(
            phone=phone,
            channel=ChannelType.WHATSAPP,
            raw_text=body.strip(),
            received_at=datetime.now(timezone.utc),
            display_name=profile_name or "",
            message_id=message_sid or "",
            media_url=media_url,
            media_type=media_type,
        )

    # ── Saída: OutboundMessage → TwiML (resposta síncrona ao webhook) ─────────

    def render(self, outbound: OutboundMessage) -> str:
        """
        Converte OutboundMessage em TwiML para a resposta HTTP ao webhook.

        Limite prático: 1.600 chars por mensagem WhatsApp Business.
        O TwiML aceita qualquer tamanho, mas mensagens longas são fragmentadas.
        """
        return outbound.to_twiml()

    def render_empty(self) -> str:
        """TwiML vazio — não envia mensagem, apenas confirma recebimento."""
        return "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"

    # ── Segurança: valida assinatura Twilio ───────────────────────────────────

    def verify_signature(self, request_url: str, params: dict, signature: str) -> bool:
        """
        Valida que o POST veio realmente do Twilio.
        https://www.twilio.com/docs/usage/webhooks/webhooks-security

        Em desenvolvimento (sem auth_token), sempre retorna True.
        EM PRODUÇÃO: configurar TWILIO_AUTH_TOKEN no .env.
        """
        if not settings.twilio_auth_token:
            logger.warning("twilio_signature_skipped — TWILIO_AUTH_TOKEN not set")
            return True

        # Twilio: concatena URL + params em ordem alfabética, assina com HMAC-SHA1
        payload = request_url
        for key in sorted(params.keys()):
            payload += key + str(params[key])

        expected = base64.b64encode(
            hmac.new(
                settings.twilio_auth_token.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")

        return hmac.compare_digest(expected, signature)


# ── Singleton por processo ────────────────────────────────────────────────────

_adapter = TwilioAdapter()


def get_twilio_adapter() -> TwilioAdapter:
    return _adapter
