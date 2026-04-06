"""
whatsapp_handler.py — Webhook HTTP do Twilio WhatsApp.

RESPONSABILIDADE ÚNICA:
  Receber POST do Twilio → parse → InboundMessage → route → OutboundMessage → TwiML

GARANTIA:
  Sempre retorna HTTP 200. Qualquer erro interno vira mensagem amigável.
  O Twilio re-tenta em 4xx/5xx, causando mensagens duplicadas.

FLUXO DETALHADO:
  ┌─────────────────────────────────────────────────────┐
  │  POST /webhook/whatsapp  (Twilio, form-data)        │
  │                                                     │
  │  1. verify_signature()  — valida que veio do Twilio │
  │  2. adapter.parse()     — Twilio → InboundMessage   │
  │  3. sessions.resolve()  — phone → group_id          │
  │  4. route_message()     — IntentType → handler      │
  │  5. sessions.update()   — atualiza contexto sessão  │
  │  6. adapter.render()    — OutboundMessage → TwiML   │
  │                                                     │
  │  HTTP 200 + TwiML                                   │
  └─────────────────────────────────────────────────────┘
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Response, Request

from .contracts import OutboundMessage, DeliveryEvent, ChannelType, DeliveryStatus
from .whatsapp_adapter import get_twilio_adapter
from .session_manager import get_session_manager
from .message_router import MessageRouter
from ..language.fallback_templates import build_error_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["channel"])

# Singleton do router — criado uma vez por processo
_message_router = MessageRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From:        str = Form(...),
    Body:        str = Form(default=""),
    ProfileName: str = Form(default=""),
    MessageSid:  str = Form(default=""),
    NumMedia:    str = Form(default="0"),
    MediaUrl0:   str = Form(default=""),
    MediaContentType0: str = Form(default=""),
):
    """
    Webhook principal — chamado a cada mensagem recebida.
    Twilio espera HTTP 200 + TwiML em até 15 segundos.
    """
    adapter  = get_twilio_adapter()
    sessions = get_session_manager()

    # ── 1. Parse: campos Twilio → InboundMessage ──────────────────────────────
    inbound = adapter.parse(
        from_field=From,
        body=Body,
        profile_name=ProfileName,
        message_sid=MessageSid,
        num_media=NumMedia,
        media_url=MediaUrl0 or None,
        media_content_type=MediaContentType0 or None,
    )

    if inbound.is_empty:
        logger.debug("empty_message_ignored phone=%s", inbound.phone)
        return Response(content=adapter.render_empty(), media_type="text/xml")

    # ── 2. Enriquece com group_id da sessão ───────────────────────────────────
    inbound.group_id = sessions.resolve(inbound.phone)

    logger.info(
        "whatsapp_inbound phone=%s group=%s new_user=%s msg='%s'",
        inbound.phone, inbound.group_id, inbound.is_new_user,
        inbound.truncated_text,
    )

    # ── 3. Roteamento → OutboundMessage ───────────────────────────────────────
    try:
        outbound = await _message_router.route(inbound)
    except Exception as e:
        logger.error(
            "route_failed phone=%s msg='%s' error=%s",
            inbound.phone, inbound.truncated_text, e, exc_info=True,
        )
        outbound = OutboundMessage(
            to_phone=inbound.phone,
            channel=ChannelType.WHATSAPP,
            text=build_error_message(),
            fallback_used=True,
            delivery_status=DeliveryStatus.FALLBACK,
        )

    # ── 4. Atualiza contexto de sessão ────────────────────────────────────────
    if outbound.intent_handled:
        sessions.update_context(
            inbound.phone,
            intent=outbound.intent_handled,
        )

    logger.info(
        "whatsapp_outbound phone=%s intent=%s fallback=%s llm=%s chars=%d",
        inbound.phone, outbound.intent_handled,
        outbound.fallback_used, outbound.used_llm, outbound.char_count,
    )

    # ── 5. Render: OutboundMessage → TwiML ────────────────────────────────────
    return Response(
        content=adapter.render(outbound),
        media_type="text/xml",
    )


@router.post("/webhook/whatsapp/status")
async def whatsapp_status_callback(
    MessageSid: str = Form(default=""),
    MessageStatus: str = Form(default=""),
    To: str = Form(default=""),
    ErrorCode: str = Form(default=""),
    ErrorMessage: str = Form(default=""),
):
    """
    Callback de status do Twilio — recebe atualizações de entrega.
    Configurado no painel Twilio como "Status Callback URL".

    Eventos recebidos: queued → sent → delivered (ou failed).
    """
    event = DeliveryEvent(
        message_sid=MessageSid,
        to_phone=To.replace("whatsapp:", "").strip(),
        status=MessageStatus,
        error_code=ErrorCode or None,
        error_message=ErrorMessage or None,
    )

    if event.status == "delivered":
        logger.info("delivery_confirmed sid=%s phone=%s", event.message_sid, event.to_phone)
    elif event.status in ("failed", "undelivered"):
        logger.warning(
            "delivery_failed sid=%s phone=%s code=%s msg=%s",
            event.message_sid, event.to_phone, event.error_code, event.error_message,
        )

    # HTTP 204 — Twilio não processa a resposta deste callback
    return Response(status_code=204)


@router.get("/webhook/whatsapp")
async def whatsapp_verify():
    """
    Twilio faz GET durante configuração para validar que o webhook existe.
    """
    return Response(content="OK", media_type="text/plain")
