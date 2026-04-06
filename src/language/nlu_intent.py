"""
nlu_intent.py — Classificador de intenção por regras e heurísticas.

ARQUITETURA:
  Cada IntentType tem um conjunto de sinais positivos (indicam a intenção)
  e sinais negativos (contradizem). O classificador pontua cada intenção
  e retorna a de maior score com a confiança calculada.

  Confiança = score_vencedor / (score_vencedor + score_segundo_lugar)
  → Alta quando a diferença entre 1º e 2º é grande.
  → Baixa quando dois candidatos têm scores parecidos (ambiguidade real).

ADICIONANDO UMA NOVA INTENÇÃO:
  1. Adicione o valor ao IntentType enum (domain/enums/intent.py)
  2. Crie uma IntentSignal com seus sinais
  3. Adicione ao ALL_SIGNALS
  4. Adicione casos ao test_intent_classifier.py
"""

import re
from dataclasses import dataclass, field
from ..domain.enums import IntentType
from .nlu_knowledge import normalize


@dataclass
class IntentSignal:
    """Define os sinais que caracterizam uma intenção."""
    intent: IntentType
    # Frases ou palavras que aumentam o score (verificadas por substring)
    positive: list[str] = field(default_factory=list)
    # Padrões regex para sinais mais precisos
    regex_positive: list[str] = field(default_factory=list)
    # Presença destes tokens REDUZ o score desta intenção
    negative: list[str] = field(default_factory=list)
    # Peso base da intenção (raramente mude — prefira ajustar os sinais)
    base_weight: float = 1.0


ALL_SIGNALS: list[IntentSignal] = [

    IntentSignal(
        intent=IntentType.CHECK_IN,
        positive=[
            "chegamos no parque", "chegou no parque", "chegamos no magic",
            "chegamos", "acabamos de chegar",
            "acabei de chegar", "entramos", "acabamos de entrar",
            "estamos aqui", "oi", "ola", "olá", "bom dia", "boa tarde",
            "boa noite", "primeiro dia", "comecando", "começando",
        ],
        regex_positive=[
            r"\bchegamos\b.*\bparque\b",
            r"\bchegou?\b",
            r"\bentramos?\b",
            r"\bcomec(ou|amos)\b",
        ],
        negative=["saindo", "fomos embora", "terminamos"],
        base_weight=1.0,
    ),

    IntentSignal(
        intent=IntentType.GET_REC,
        positive=[
            "onde vamos", "onde ir", "o que fazer", "o que fazemos",
            "proxima atracao", "próxima atração", "sugere", "sugestao",
            "sugestão", "recomenda", "recomendacao", "recomendação",
            "qual a proxima", "qual proxima", "para onde", "qual vamos",
            "tem alguma sugestao", "tem alguma sugestão", "o que tem bom",
            "o que tem aqui", "quais as melhores", "qual seria",
            "me indica", "me ajuda a decidir", "ajuda a escolher",
        ],
        regex_positive=[
            r"\bpara\s+onde\b",
            r"\bo\s+que\s+(fazer|fazemos|vamos)\b",
            r"\bonde\s+(ir|vamos|vamos\s+agora)\b",
            r"\bqual\s+(atracao|atração|brinquedo|proxim)\b",
        ],
        negative=[],
        base_weight=1.2,  # intenção mais comum — leve boost
    ),

    IntentSignal(
        intent=IntentType.EVAL_QUEUE,
        positive=[
            "vale a pena", "vale essa fila", "compensa", "vale esperar",
            "muito tempo", "muito espera", "ta valendo", "tá valendo",
            "minutos de fila", "de fila", "fila de", "fila ta",
            "fila tá", "fila esta", "fila está",
            "vale a espera", "compensar",
        ],
        regex_positive=[
            r"\bvale\b.*\bfila\b",
            r"\bfila\b.*\b\d+\s*min",
            r"\b\d+\s*min\b.*\bvale\b",
            r"\bcompensa\b.*\besperar\b",
        ],
        negative=[],
        base_weight=1.0,
    ),

    IntentSignal(
        intent=IntentType.UPDATE_LOC,
        positive=[
            "estamos na", "estamos em", "estamos no", "estamos perto",
            "chegamos na", "chegamos em", "chegamos no",
            "saindo do", "saindo da", "acabamos de sair",
            "agora estamos", "nos estamos", "já estamos",
            "passando pela", "passando pelo", "perto do", "perto da",
        ],
        regex_positive=[
            r"\bestamos\s+(na|no|em|perto|aqui)\b",
            r"\bchegamos\s+(na|no|em|ao)\b",
            r"\bsaindo\s+(do|da)\b",
        ],
        negative=["onde vamos", "o que fazer", "o que fazemos"],
        base_weight=1.0,
    ),

    IntentSignal(
        intent=IntentType.UPDATE_STATE,
        positive=[
            "cansou", "cansamos", "cansada", "cansado", "esgotados",
            "com fome", "queremos comer", "precisamos comer",
            "calor demais", "muito calor", "suando",
            "molhados", "ficamos molhados",
            "crianca choran", "criança choran", "fazendo birra",
            "precisando descansar", "queremos descansar",
            "dar uma pausa", "parar um pouco",
        ],
        regex_positive=[
            r"\bcanso\w*\b",
            r"\bfom\w*\b",
            r"\bcalor\b",
            r"\bmolhad\w*\b",
        ],
        negative=["onde vamos", "o que fazer"],
        base_weight=1.0,
    ),

    IntentSignal(
        intent=IntentType.FILTER_REQ,
        positive=[
            "queremos algo leve", "algo mais tranquilo", "coisa leve",
            "so indoor", "só indoor", "com ar condicionado", "clima tizado",
            "sem fila longa", "fila curta", "fila rapida", "fila rápida",
            "ate 20 minutos", "até 20 minutos", "ate 30 minutos", "até 30 minutos",
            "por favor", "so quero", "so queremos", "apenas",
            "nao muito forte",
            "não muito forte", "mais suave", "menos radical",
            "que todos possam", "que a crianca possa", "que a criança possa",
            "todo mundo pode", "sem restricao de altura",
        ],
        regex_positive=[
            r"\bso\s+(indoor|outdoor|coberto)\b",
            r"\bate\s+\d+\s*min\b",
            r"\balgo\s+(leve|tranquilo|suave)\b",
            r"\bcoisa\s+(leve|tranquila|suave)\b",
        ],
        negative=[],
        base_weight=1.0,
    ),

    IntentSignal(
        intent=IntentType.MARK_DONE,
        positive=[
            "saindo do", "saindo da", "acabamos de fazer",
            "fizemos", "fizemos o", "fizemos a",
            "acabamos de sair", "ja fizemos", "já fizemos",
            "acabou", "terminou", "terminamos", "foi incrivel",
            "foi otimo", "foi ótimo", "adoramos", "amamos",
            "acabamos de fazer", "saímos do", "saímos da",
            "acabei de fazer", "acabei de sair",
        ],
        regex_positive=[
            r"\bfizemos\b",
            r"\bsaindo\s+(do|da)\b",
            r"\bsaimos\s+(do|da)\b",
            r"\bacabamos\s+de\s+(fazer|sair)\b",
        ],
        negative=["onde vamos", "vale a pena"],
        base_weight=1.1,
    ),

    IntentSignal(
        intent=IntentType.QUESTION,
        positive=[
            "quanto tempo", "quanto demora", "qual a altura",
            "altura minima", "altura mínima", "precisa de quantos",
            "quanto mede", "tem restricao", "tem restrição",
            "moja", "molha", "molha muito", "assusta",
            "assusta muito", "e muito assustador", "é muito assustador",
            "tem fila", "como e", "como é", "me conta sobre",
            "o que e", "o que é", "o que tem",
            "cadeirante pode", "cadeirante entra", "bebe pode", "bebê pode",
        ],
        regex_positive=[
            r"\bquanto\s+(tempo|dura|demora|min)\b",
            r"\bqual\s+a\s+altura\b",
            r"\bmolha\b",
            r"\bassusta\b",
            r"\bpode\s+entrar\b",
        ],
        negative=[],
        base_weight=1.0,
    ),
]


@dataclass
class ClassificationResult:
    intent: IntentType
    confidence: float
    scores: dict[str, float]
    matched_signals: list[str]


def classify_intent(text: str) -> ClassificationResult:
    """
    Classifica a intenção da mensagem.

    Retorna ClassificationResult com:
      - intent: intenção vencedora
      - confidence: 0.0–1.0
      - scores: scores de todas as intenções (para debug)
      - matched_signals: sinais que contribuíram para o vencedor
    """
    norm = normalize(text)
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for signal in ALL_SIGNALS:
        score = 0.0
        hits = []

        for phrase in signal.positive:
            if phrase in norm:
                score += 1.0
                hits.append(phrase)

        for pattern in signal.regex_positive:
            if re.search(pattern, norm):
                score += 1.5  # regex pesa mais por ser mais preciso
                hits.append(f"/{pattern}/")

        for neg in signal.negative:
            if neg in norm:
                score -= 0.8

        score *= signal.base_weight
        key = signal.intent.value
        scores[key] = max(0.0, score)
        matched[key] = hits

    if not any(s > 0 for s in scores.values()):
        return ClassificationResult(
            intent=IntentType.UNKNOWN,
            confidence=0.0,
            scores=scores,
            matched_signals=[],
        )

    # Ordena por score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_key, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # Confiança: proporção do gap entre 1º e 2º
    if best_score + second_score == 0:
        confidence = 0.5
    else:
        confidence = best_score / (best_score + second_score)
    confidence = min(0.98, round(confidence, 3))

    # Aplica teto de confiança por número de sinais
    total_hits = len(matched.get(best_key, []))
    if total_hits == 1:
        confidence = min(confidence, 0.80)
    elif total_hits == 0:
        confidence = min(confidence, 0.60)

    return ClassificationResult(
        intent=IntentType(best_key),
        confidence=confidence,
        scores={k: round(v, 2) for k, v in scores.items() if v > 0},
        matched_signals=matched.get(best_key, []),
    )
