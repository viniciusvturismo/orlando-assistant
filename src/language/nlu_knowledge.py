"""
nlu_knowledge.py — Base de conhecimento do interpretador.

Centraliza todos os vocabulários, mapeamentos e padrões linguísticos
usados pelas regras de extração. Manter aqui facilita:
  - adicionar novos parques (novo bloco ATTRACTION_SLUGS + AREA_PATTERNS)
  - adicionar variações de PT-BR coloquial sem tocar na lógica
  - auditar cobertura linguística sem ler código

CONVENÇÃO:
  - Todas as chaves de dicionário em minúsculas e sem acento (após normalize())
  - Valores são sempre slugs ou enums do domínio
  - Listas de padrões em ordem decrescente de especificidade
"""

# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

import re
import unicodedata


def normalize(text: str) -> str:
    """
    Remove acentos, converte para minúsculas e colapsa espaços.
    Usado antes de qualquer lookup neste módulo.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


# ─────────────────────────────────────────────────────────────────────────────
# ÁREAS DO PARQUE
# Mapeamento de referências coloquiais → slug canônico
# ─────────────────────────────────────────────────────────────────────────────

AREA_ALIASES: dict[str, str] = {
    # Main Street
    "main street": "main_street",
    "main": "main_street",
    "entrada": "main_street",
    "portao": "main_street",
    "portão": "main_street",
    "emporium": "main_street",

    # Fantasyland
    "fantasyland": "fantasyland",
    "castelo": "fantasyland",
    "perto do castelo": "fantasyland",
    "proximo ao castelo": "fantasyland",
    "cinderela": "fantasyland",
    "princesas": "fantasyland",
    "peter pan": "fantasyland",
    "small world": "fantasyland",
    "it's a small world": "fantasyland",

    # Tomorrowland
    "tomorrowland": "tomorrowland",
    "space mountain": "tomorrowland",
    "buzz lightyear": "tomorrowland",
    "tron": "tomorrowland",
    "area do futuro": "tomorrowland",
    "area futurista": "tomorrowland",

    # Frontierland
    "frontierland": "frontierland",
    "big thunder": "frontierland",
    "thunder mountain": "frontierland",
    "splash": "frontierland",
    "tiana": "frontierland",
    "area do oeste": "frontierland",
    "velho oeste": "frontierland",

    # Adventureland
    "adventureland": "adventureland",
    "piratas": "adventureland",
    "pirates": "adventureland",
    "jungle cruise": "adventureland",
    "area da aventura": "adventureland",

    # Liberty Square
    "liberty square": "liberty_square",
    "haunted mansion": "liberty_square",
    "mansao": "liberty_square",
    "casa mal assombrada": "liberty_square",
    "area historica": "liberty_square",

    # Storybook Circus
    "storybook circus": "storybook_circus",
    "dumbo": "storybook_circus",
    "circo": "storybook_circus",
    "area do circo": "storybook_circus",
}


def resolve_area(text: str) -> tuple[str | None, str | None]:
    """
    Tenta resolver uma referência textual para um slug de área.
    Retorna (slug, ref_text_original) ou (None, None).
    Busca por substring — não exige match exato.
    """
    norm = normalize(text)
    # Busca do mais específico (frases) para o menos (palavras)
    for alias in sorted(AREA_ALIASES.keys(), key=len, reverse=True):
        if alias in norm:
            return AREA_ALIASES[alias], alias
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# ATRAÇÕES
# Mapeamento de referências coloquiais → slug canônico
# ─────────────────────────────────────────────────────────────────────────────

ATTRACTION_ALIASES: dict[str, str] = {
    # Seven Dwarfs Mine Train
    "mine train": "seven_dwarfs_mine_train",
    "montanha dos anoes": "seven_dwarfs_mine_train",
    "montanha dos sete anoes": "seven_dwarfs_mine_train",
    "montanha russa dos anoes": "seven_dwarfs_mine_train",
    "seven dwarfs": "seven_dwarfs_mine_train",
    "sete anoes": "seven_dwarfs_mine_train",

    # Space Mountain
    "space mountain": "space_mountain",
    "space": "space_mountain",
    "montanha do espaco": "space_mountain",

    # Tron Lightcycle Run
    "tron": "tron_lightcycle_run",
    "tron lightcycle": "tron_lightcycle_run",
    "tron run": "tron_lightcycle_run",
    "lightcycle": "tron_lightcycle_run",

    # Big Thunder Mountain
    "big thunder": "big_thunder_mountain",
    "big thunder mountain": "big_thunder_mountain",
    "thunder mountain": "big_thunder_mountain",
    "thunder": "big_thunder_mountain",
    "montanha do trovao": "big_thunder_mountain",

    # Haunted Mansion
    "haunted mansion": "haunted_mansion",
    "haunted": "haunted_mansion",
    "casa mal assombrada": "haunted_mansion",
    "mansao assombrada": "haunted_mansion",
    "mansao": "haunted_mansion",
    "casa dos fantasmas": "haunted_mansion",
    "fantasmas": "haunted_mansion",

    # Pirates of the Caribbean
    "pirates": "pirates_of_the_caribbean",
    "pirates of the caribbean": "pirates_of_the_caribbean",
    "piratas do caribe": "pirates_of_the_caribbean",
    "piratas": "pirates_of_the_caribbean",
    "pirata": "pirates_of_the_caribbean",

    # Peter Pan's Flight
    "peter pan": "peter_pan_flight",
    "voo do peter pan": "peter_pan_flight",

    # it's a small world
    "small world": "its_a_small_world",
    "it's a small world": "its_a_small_world",
    "mundo pequeno": "its_a_small_world",
    "e um mundo pequeno": "its_a_small_world",

    # Buzz Lightyear
    "buzz lightyear": "buzz_lightyear",
    "buzz": "buzz_lightyear",

    # Dumbo
    "dumbo": "dumbo",
    "elefante voador": "dumbo",

    # Tiana's Bayou Adventure
    "tiana": "tiana_bayou_adventure",
    "tiana's bayou": "tiana_bayou_adventure",
    "bayou": "tiana_bayou_adventure",
    "pantano da tiana": "tiana_bayou_adventure",
    "splash mountain": "tiana_bayou_adventure",  # antigo nome, redireciona

    # Jungle Cruise
    "jungle cruise": "jungle_cruise",
    "selva": "jungle_cruise",
    "cruzeiro pela selva": "jungle_cruise",
}


def resolve_attraction(text: str) -> tuple[str | None, str | None]:
    """
    Tenta resolver referência textual para slug de atração.
    Retorna (slug, texto_original) ou (None, None).
    """
    norm = normalize(text)
    for alias in sorted(ATTRACTION_ALIASES.keys(), key=len, reverse=True):
        if alias in norm:
            return ATTRACTION_ALIASES[alias], alias
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# ESTADOS DO GRUPO
# Sinais de condição física ou emocional
# ─────────────────────────────────────────────────────────────────────────────

STATE_PATTERNS: dict[str, list[str]] = {
    "tired": [
        "canso", "cansou", "cansad", "cansanc", "nao aguent", "não aguent",
        "esgot", "exaust", "sem energia", "sem folego", "sem fôlego",
        "precisando descansar", "precisa descansar", "queremos descansar",
        "quero descansar", "querendo sentar", "quero sentar",
    ],
    "hungry": [
        "fome", "comer", "almocar", "almoçar", "jantar", "lanche",
        "restaurante", "comida", "com fome", "precisando comer",
        "hora de comer", "hora do almoco", "hora do almoço",
    ],
    "hot": [
        "calor", "calor demais", "muito calor", "suando", "suor",
        "quente demais", "derretendo", "tá quente", "ta quente",
        "morendo de calor", "achando muito calor",
    ],
    "wet": [
        "molhad", "encharcad", "ensopado", "pegamos chuva", "choveu",
        "ficamos molhados", "tudo molhado",
    ],
    "cranky": [
        "birra", "choran", "mal humorad", "irritad", "nervos",
        "estressad", "passando mal", "chorosa", "choroso",
    ],
    "needs_rest": [
        "pausa", "descanso", "sentar", "precisamos sentar", "queremos parar",
        "dar uma pausa", "tomar agua", "banheiro",
    ],
}


def extract_states(text: str) -> list[str]:
    """
    Extrai estados do grupo mencionados na mensagem.
    Retorna lista de strings de estado (nomes do GroupStateType).
    """
    norm = normalize(text)
    found = []
    for state, patterns in STATE_PATTERNS.items():
        if any(p in norm for p in patterns):
            found.append(state)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# FILTROS MOMENTÂNEOS
# Restrições e preferências temporárias expressas na mensagem
# ─────────────────────────────────────────────────────────────────────────────

INTENSITY_LOW_PATTERNS = [
    "leve", "tranquilo", "tranquila", "suave", "calmo", "calma",
    "sem emocao", "sem emoção", "sem adrenalina", "mais parado",
    "mais tranquilo", "coisa leve", "algo leve", "algo tranquilo",
    "nada radical", "nao radical", "sem barulho",
]

INTENSITY_HIGH_PATTERNS = [
    "adrenalina", "radical", "emocao", "emoção", "forte", "pesado",
    "intenso", "intensa", "nervoso", "nervosa", "algo forte",
    "coisa forte", "brinquedo forte", "brinquedo radical",
]

INDOOR_PATTERNS = [
    "indoor", "coberto", "coberta", "climatizad", "ar condicionado",
    "com ac", "gelad", "frio", "com frescor", "fechado", "fechada",
    "dentro", "sob cobertura", "com sombra", "na sombra",
]

OUTDOOR_PATTERNS = [
    "outdoor", "ar livre", "ao ar livre", "descoberto", "aberto",
    "fora", "ao sol",
]

FOR_ALL_PATTERNS = [
    "todos possam", "todo mundo", "que todos", "inclusive",
    "a familia toda", "a família toda", "crianca tambem", "criança também",
    "sem restricao", "sem restrição", "sem altura minima", "qualquer um",
]


def extract_filter_override(text: str) -> dict | None:
    """
    Extrai restrição ou preferência momentânea da mensagem.
    Retorna dict com campos relevantes, ou None se nada encontrado.
    """
    norm = normalize(text)

    intensity = None
    if any(p in norm for p in INTENSITY_LOW_PATTERNS):
        intensity = "low"
    elif any(p in norm for p in INTENSITY_HIGH_PATTERNS):
        intensity = "high"

    environment = None
    if any(p in norm for p in INDOOR_PATTERNS):
        environment = "indoor"
    elif any(p in norm for p in OUTDOOR_PATTERNS):
        environment = "outdoor"

    for_all = any(p in norm for p in FOR_ALL_PATTERNS)

    # Extrai limite numérico de fila se mencionado
    max_queue = _extract_queue_limit(norm)

    if any([intensity, environment, for_all, max_queue is not None]):
        return {
            "intensity": intensity,
            "environment": environment,
            "for_all_members": for_all,
            "max_queue_minutes": max_queue,
        }
    return None


def _extract_queue_limit(norm: str) -> int | None:
    """Extrai limite de fila de expressões como 'até 20 minutos' ou 'menos de 30 min'."""
    patterns = [
        r"ate\s+(\d+)\s*min",
        r"no maximo\s+(\d+)\s*min",
        r"menos de\s+(\d+)\s*min",
        r"abaixo de\s+(\d+)\s*min",
        r"(\d+)\s*min(utos)?\s*(no maximo|de espera|de fila)",
    ]
    import re as _re
    for pattern in patterns:
        m = _re.search(pattern, norm)
        if m:
            val = int(m.group(1))
            if 5 <= val <= 180:
                return val
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MEMBROS DO GRUPO
# Extração de idades, alturas e roles mencionados
# ─────────────────────────────────────────────────────────────────────────────

ROLE_WORDS: dict[str, str] = {
    "bebe": "infant",
    "bebê": "infant",
    "nenem": "infant",
    "nenê": "infant",
    "filho": "child",
    "filha": "child",
    "crianca": "child",
    "criança": "child",
    "menino": "child",
    "menina": "child",
    "meu marido": "adult",
    "minha esposa": "adult",
    "meu esposo": "adult",
    "minha mulher": "adult",
    "avo": "senior",
    "avô": "senior",
    "avo": "senior",
    "avó": "senior",
    "vovo": "senior",
    "vovô": "senior",
    "vovó": "senior",
    "idoso": "senior",
    "idosa": "senior",
}

import re as _re


def extract_members(text: str) -> list[dict]:
    """
    Extrai membros mencionados com role, age e height_cm quando disponíveis.
    Exemplos: "filha de 7 anos", "criança de 105cm", "duas crianças de 6 e 9 anos"
    """
    members = []
    norm = normalize(text)

    # Padrão: role + de + idade
    # Ex: "filha de 7 anos", "filho de 9 anos e 112cm"
    age_pattern = _re.compile(
        r"(filho|filha|crianca|criança|menino|menina|bebe|bebê|nenem)\s+"
        r"(?:de\s+)?(\d{1,2})\s*anos?"
    )
    for match in age_pattern.finditer(norm):
        role_word = match.group(1)
        age = int(match.group(2))
        role = "infant" if age < 2 else "child"
        member = {"role": role, "age": age}

        # Tenta capturar altura próxima
        height = _extract_nearby_height(norm, match.end())
        if height:
            member["height_cm"] = height

        members.append(member)

    # Padrão: número + crianças + de + idades separadas por "e" ou ","
    # Ex: "duas crianças de 6 e 9 anos"
    multi_pattern = _re.compile(
        r"(\d+|duas?|tres?|quatro)\s+(?:criancas?|crianças?)\s+de\s+([\d\s,e]+)\s*anos?"
    )
    for match in multi_pattern.finditer(norm):
        ages_str = match.group(2)
        ages = [int(a) for a in _re.findall(r"\d+", ages_str) if int(a) <= 17]
        for age in ages:
            if not any(m.get("age") == age for m in members):
                members.append({"role": "child", "age": age})

    # Padrão: somos X pessoas / somos X adultos
    adults_pattern = _re.compile(r"(?:somos\s+)?(\d+)\s+adultos?")
    for match in adults_pattern.finditer(norm):
        count = int(match.group(1))
        existing_adults = sum(1 for m in members if m["role"] == "adult")
        for _ in range(count - existing_adults):
            members.append({"role": "adult"})

    # Padrão: menção de bebê sem idade
    if "bebe" in norm or "bebê" in norm or "nenem" in norm or "nenê" in norm:
        if not any(m["role"] == "infant" for m in members):
            members.append({"role": "infant"})

    return members


def _extract_nearby_height(text: str, start_pos: int) -> int | None:
    """Procura altura (cm) nos próximos 30 chars após a posição dada."""
    window = text[start_pos:start_pos + 30]
    m = _re.search(r"(\d{2,3})\s*cm", window)
    if m:
        val = int(m.group(1))
        if 50 <= val <= 200:
            return val
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FILA REPORTADA
# Extração de tempo de espera mencionado pelo usuário
# ─────────────────────────────────────────────────────────────────────────────

QUEUE_PATTERNS = [
    r"(\d+)\s*min(?:utos)?\s+de\s+(?:fila|espera)",
    r"fila\s+de\s+(\d+)\s*min",
    r"(\d+)\s*min(?:utos)?\s+de\s+fila",
    r"espera\s+de\s+(\d+)",
    r"(\d+)\s*h(?:oras?)?\s+de\s+fila",   # horas → converte para min
    r"quase\s+(\d+)\s*h(?:oras?)?",
    r"uns\s+(\d+)\s*min",
    r"mais\s+de\s+(\d+)\s*min",
]


def extract_wait_minutes(text: str) -> int | None:
    """
    Extrai tempo de fila explícito. Retorna int em minutos ou None.
    NUNCA retorna valor para expressões qualitativas como "fila enorme".
    """
    norm = normalize(text)
    for pattern in QUEUE_PATTERNS:
        m = _re.search(pattern, norm)
        if m:
            val = int(m.group(1))
            # Se o padrão era de horas, converte
            if "h" in pattern and val <= 5:
                val *= 60
            if 0 <= val <= 300:
                return val
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENTO
# ─────────────────────────────────────────────────────────────────────────────

SENTIMENT_POSITIVE = [
    "incrivel", "incrível", "otimo", "ótimo", "amamos", "adoramos", "gostamos",
    "foi demais", "foi muito bom", "muito bom", "perfeito", "show", "valeu",
    "sensacional", "maravilhoso", "top", "mandou bem", "superou", "amo",
]
SENTIMENT_NEGATIVE = [
    "nao gostei", "não gostei", "ruim", "pessimo", "péssimo", "decepcionou",
    "decepcionante", "fraco", "muito ruim", "nao gostamos", "não gostamos",
    "nao valeu", "não valeu", "nao curti", "não curti",
]


def extract_sentiment(text: str) -> str | None:
    """Retorna 'positive', 'negative' ou None."""
    norm = normalize(text)
    if any(p in norm for p in SENTIMENT_POSITIVE):
        return "positive"
    if any(p in norm for p in SENTIMENT_NEGATIVE):
        return "negative"
    return None
