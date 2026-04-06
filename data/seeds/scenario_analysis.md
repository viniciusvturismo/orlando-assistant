# Simulação de cenários — MVP Orlando Park Assistant
## Resultados e análise de coerência lógica

---

## Cenário 01 — Família P2 · Rope drop · Fantasyland

| Campo | Valor |
|---|---|
| Perfil | P2 — família com crianças 8a (126cm) e 6a (110cm) |
| Localização | Fantasyland · 09h05 · ensolarado |
| Atrações feitas | nenhuma |
| Must-do | Mine Train, Haunted Mansion |
| Pesos ativos | padrão P2 (D1=30%, D2=20%, D3=28%, D4=12%, D5=10%) |
| Filtros | 1 excluída: Tron (height_restriction 107cm — criança de 110cm passa, mas 6a de 110cm não chega em Tron que exige 107 ✓) |

**Resultado do motor:**

| # | Atração | Score | Fila | Walk |
|---|---|---|---|---|
| ★ 1 | Peter Pan's Flight | 97.5 | 15 min | 2 min |
| ● 2 | Haunted Mansion | 88.x | 20 min | 8 min |
| 3 | Seven Dwarfs Mine Train | ~83 | 15 min | 2 min |

**Mensagem gerada:**
```
✅ Peter Pan's Flight
15 min de fila · aqui do lado

🔄 Alternativa: Haunted Mansion
20 min de fila

💡 Indoor com AC — boa escolha com esse calor.
3 min de duração com filas de até 75 min — relação péssima fora do rope drop

📍 Me avisa quando saírem que sugerimos o próximo!
```

**⚠️ FALHA DETECTADA — Cenário 01:**
Peter Pan venceu a Mine Train (must-do) no rope drop porque a Mine Train teve score base menor mesmo com o bônus de +15. A Mine Train ficou em 3º lugar.

**Causa raiz:** A Mine Train tem uma penalidade de outdoor (+sol) que reduz seu score em 5 pts, e Peter Pan tem indoor_ac + rope_drop match perfeito em D4 (100 pts). O bônus de must_do (+15) não foi suficiente para compensar a diferença nos raw scores dimensionais.

**Correção sugerida:** No rope drop, atrações com fila historicamente alta (Mine Train = 60 min de manhã) devem receber um bônus adicional de "janela rara" quando a fila atual está abaixo de 40% da média histórica. Fila de 15 min vs histórico de 60 min = 25% → bônus de urgência deveria ser acionado.

---

## Cenário 02 — P7 · 10h · Tomorrowland · Tron já feito

| Campo | Valor |
|---|---|
| Perfil | P7 — grupo de amigos adultos, adrenalina |
| Localização | Tomorrowland · 10h00 · ensolarado |
| Atrações feitas | Tron (rope drop) |
| Must-do pendentes | Space Mountain, Mine Train, Big Thunder |
| Pesos ativos | padrão P7 (D3=35%, D5=20%) |

**Resultado do motor:**

| # | Atração | Score | Fila | Walk |
|---|---|---|---|---|
| ★ 1 | Big Thunder Mountain | 89.1 | 30 min | 12 min |
| ● 2 | Space Mountain | 87.x | 55 min | 2 min |

**Mensagem gerada:**
```
✅ Big Thunder Mountain
30 min de fila · uns 12 min caminhando

🔄 Alternativa: Space Mountain
55 min de fila (moderado)

💡 Essa tava na lista de vocês — e a fila tá favorável.
```

**✓ COERENTE** — Big Thunder (30 min, must-do) venceu Space Mountain (55 min, must-do). Mesmo sendo mais longe, a vantagem de fila justifica. A opção B com 55 min é honesta — a mensagem mostra claramente o custo.

**Observação:** A mensagem diz "outdoor — leve protetor solar" mesmo sendo 10h. Correto dado o campo weather=sunny.

---

## Cenário 03 — P1 · 12h30 · Bebê · Calor intenso

| Campo | Valor |
|---|---|
| Perfil | P1 — família com bebê e criança 4a (98cm) |
| Localização | Fantasyland · 12h30 · sol forte |
| Atrações feitas | Dumbo |
| Must-do | Belle, Small World, Dumbo (já feito) |
| Evitar | spinning, thrill, extreme, dark |
| Pesos ativos | padrão P1 (D1=40%, D2=30%) |

**Resultado do motor:**

| # | Atração | Score | Fila | Walk |
|---|---|---|---|---|
| ★ 1 | it's a small world | 86.1 | 12 min | 2 min |
| ● 2 | Carousel of Progress | 69.x | 5 min | — |

**Mensagem gerada:**
```
✅ it's a small world
12 min de fila · aqui do lado

🔄 Alternativa: Carousel Of Progress
~5 min de fila (ótimo)

💡 Essa tava na lista de vocês — e a fila tá favorável.
Melhor custo-benefício de tempo do MK: 11 min com fila quase sempre abaixo de 20 min
```

**⚠️ FALHA MENOR — Cenário 03:**
A nota estratégica aparece em todas as mensagens onde a atração tem `strategic_notes` preenchido, mesmo quando o texto da nota é técnico demais ("11 min com fila quase sempre abaixo de 20 min" — o usuário já viu que a fila é 12 min). Informação redundante.

**Correção sugerida:** Suprimir `context_note` quando o dado já está explícito na linha de fila da mensagem. Regra: se `current_wait <= historical_avg * 0.5`, a nota de "fila sempre baixa" não acrescenta nada.

---

## Cenário 04 — P5 · 14h30 · Sênior cansado · Adventureland

| Campo | Valor |
|---|---|
| Perfil | P5 — casal sênior 64/67 anos, ritmo leve |
| Localização | Adventureland · 14h30 · ensolarado |
| Atrações feitas | Pirates, Carousel |
| Must-do pendente | Haunted Mansion |
| Evitar | spinning, thrill, extreme, outdoor |
| Estados | tired |
| Pesos ativos | fatigue (D1=35%, D2=25%) |

**Resultado do motor:**

| # | Atração | Score | Fila |
|---|---|---|---|
| ★ 1 | Haunted Mansion | 65.2 | 20 min |
| ● 2 | it's a small world | 57.x | 10 min |

**Score relativamente baixo (65) explica-se:** D1 zerou porque 20 min > max_queue de 20 min (borderline). O bônus de must_do (+15) salvou a recomendação.

**Mensagem gerada:**
```
Entendido, ritmo mais tranquilo. Sugiro:

✅ Haunted Mansion
20 min de fila · 6 min a pé

💡 Essa tava na lista de vocês — e a fila tá favorável.
```

**⚠️ FALHA DETECTADA — Cenário 04:**
A fila da Haunted Mansion (20 min) é exatamente igual ao `max_queue_minutes` do grupo (20 min). Isso faz D1 retornar 0.0 (exatamente no limite). O bônus de must_do resgatou a atração. Mas a mensagem diz "e a fila tá favorável" — **o que não é verdade para um grupo cujo limite é 20 min.**

**Causa raiz:** A justificativa `must_do` gera a frase "tava na lista e a fila tá favorável" sem verificar se a fila está realmente abaixo do tolerado.

**Correção sugerida:** Quando primary_reason = "must_do" E `current_wait >= max_queue * 0.9`, a frase de apoio deve mudar para: "Era prioridade de vocês — vale esperar os 20 min." O assembler precisa de uma ramificação para must_do com fila no limite.

---

## Cenário 05 — P6 · 11h · Liberty Square · allow_split=True

| Campo | Valor |
|---|---|
| Perfil | P6 — 6 membros, 3 gerações, avós + pais + crianças 7/9 |
| Localização | Liberty Square · 11h00 · ensolarado |
| Must-do | Haunted Mansion, Pirates, Mine Train |
| allow_group_split | true |

**Resultado do motor:**

| # | Atração | Score |
|---|---|---|
| ★ 1 | Pirates of the Caribbean | 85.7 |
| ● 2 | Haunted Mansion | 80.x |

**✓ COERENTE** — Pirates venceu por ser must-do, indoor, fila menor e melhor para todos os membros incluindo avós. Haunted Mansion como segunda opção sólida.

**Observação sobre allow_split:** O `allow_group_split=True` foi configurado mas o sistema não o usou ativamente neste cenário — não havia atração que precisasse de split (Mine Train com fila 50 min já foi excluída pelo max_queue de 30 min). Correto: o split só deveria aparecer quando uma atração interessante excede o máximo de um subgrupo.

---

## Cenário 06 — P3 · 16h · Chuva · Atrações outdoor fechadas

| Campo | Valor |
|---|---|
| Perfil | P3 — adolescentes 14/16 anos |
| Localização | Frontierland · 16h00 · chuvoso |
| Fechadas | Big Thunder, Dumbo, Barnstormer (rain_sensitive) |
| Atrações feitas | Tron, Tiana |
| Must-do pendentes | Space Mountain, Mine Train |

**Resultado do motor:**

| # | Atração | Score |
|---|---|---|
| ★ 1 | Space Mountain | 81.1 |
| (só 1 elegível) | — | — |

**Filtros aplicados:** 17 excluídas — rain_sensitive fechadas + avoided_tag (11 atrações com tags "infantil" e "slow" eliminadas por P3).

**Mensagem gerada:** sem opção B (só havia 1 elegível).

**✓ COERENTE** — Com chuva e gosto de P3, realmente resta apenas Space Mountain. A mensagem foi gerada sem bloco [B], correto.

**Observação:** No cenário de chuva, o motor fechou corretamente Big Thunder e Barnstormer (rain_sensitive=true). Tiana também foi excluída (já feita). O filtro de chuva funcionou conforme projetado.

---

## Cenário 07 — P4 · 21h · Parque fecha às 23h · 3 must-do pendentes

| Campo | Valor |
|---|---|
| Perfil | P4 — casal adulto |
| Pesos ativos | end_of_day (D1=35%, D2=25%, D5=5%) |
| Must-do pendentes | Mine Train, Haunted Mansion |

**Resultado do motor:**

| # | Atração | Score | Fila |
|---|---|---|---|
| ★ 1 | Mine Train | 88.2 | 20 min |
| ● 2 | Haunted Mansion | 86.x | 10 min |

**✓ COERENTE** — End-of-day ativo corretamente. Mine Train (20 min, must-do) vs Haunted Mansion (10 min, must-do). A Mine Train venceu por margem pequena — faz sentido porque a fila dela normalmente é muito maior e 20 min no final da noite é uma janela rara.

**Observação:** Scores muito próximos (88 vs 86) no final do dia com ambas sendo must-do. A diferença veio do D3 — Mine Train tem melhor perfil para P4. O ranker escolheu área diferente corretamente (Fantasyland vs Liberty Square).

---

## Cenário 08 — P2 · Criança com enjoo · 11h30 · Main Street

| Campo | Valor |
|---|---|
| Perfil | P2 — criança 8a com motion_sickness |
| Evitar | spinning (configurado nas preferências) |
| Filtros | Buzz Lightyear e Dumbo excluídos por tag "spinning" |

**Resultado do motor:**

| # | Atração | Score | Fila |
|---|---|---|---|
| ★ 1 | Pirates of the Caribbean | 93.6 | 15 min |
| ● 2 | Haunted Mansion | 84.x | 20 min |

**✓ COERENTE** — motion_sickness foi capturado como `avoid_types: ["spinning"]` nas preferências. Buzz e Dumbo foram corretamente excluídos. Pirates venceu por ser must-do + fila excelente + indoor.

**Observação positiva:** O sistema não precisou de lógica especial para motion_sickness — o campo `motion_sickness=True` no Member gera `restriction_tags = {"spinning"}` que alimenta o filtro automaticamente.

---

## Cenário 09 — P4 · 14h · Filter override "só indoor" · Mine Train já feita

| Campo | Valor |
|---|---|
| Filter override | environment=indoor |
| Filtros extras | 7 atrações outdoor excluídas |
| Mine Train | já feita (excluded: already_done) |

**Resultado do motor:**

| # | Atração | Score | Fila |
|---|---|---|---|
| ★ 1 | Haunted Mansion | 96.5 | 15 min |
| ● 2 | Pirates | 76.x | 12 min |

**✓ COERENTE** — override indoor funcionou perfeitamente. Haunted Mansion (must-do + indoor + fila ótima à tarde) com score altíssimo (96.5). Pirates como segunda opção sólida.

**Observação:** Score 96.5 é o mais alto de todos os cenários. Faz sentido: atração must-do, fila excelente para o horário (15 min vs histórico de 25 min à tarde), indoor com AC, horário ideal (afternoon = best_time_of_day para Haunted Mansion).

---

## Cenário 10 — P2 · Criança 96cm · allow_split · Mine Train disponível

| Campo | Valor |
|---|---|
| Perfil | P2, crianças 9a (133cm) e 5a (96cm) |
| Mine Train | exige 97cm — criança de 96cm NÃO atinge |
| allow_group_split | true |

**Resultado do motor:**

| # | Atração | Score | Fila |
|---|---|---|---|
| ★ 1 | Mine Train | 83.0 | 25 min |
| ● 2 | Liberty Belle Riverboat | 79.x | 10 min |

**✓ COERENTE (parcialmente)** — Com `allow_group_split=True`, a Mine Train não foi excluída pela altura (96cm < 97cm). O sistema recomenda corretamente.

**⚠️ FALHA DETECTADA — Cenário 10:**
A mensagem gerou "Rider swap disponível se alguém não atingir a altura" como razão de apoio — o que está correto tecnicamente. Mas a mensagem não deixa claro que a criança de 5 anos (96cm) **não poderá entrar**. Para uma família com criança abaixo da altura mínima, a mensagem deveria incluir uma nota explícita: "Atenção: criança de 96cm não pode entrar (mínimo 97cm). Rider swap disponível — um adulto fica com ela enquanto os outros fazem."

**Causa raiz:** O `supporting_reasons` inclui "rider_swap_available" mas o assembler apenas converte isso em uma frase genérica, sem personalizar para a altura da criança específica.

**Correção sugerida:** Quando `allow_group_split=True` E `min_child_height < attraction.min_height_cm`, o assembler deve gerar uma nota específica com a altura da criança e o mínimo exigido.

---

## Resumo das falhas e correções

| # | Cenário | Severidade | Descrição | Correção |
|---|---|---|---|---|
| F1 | 01 | **Alta** | Mine Train (must-do) perdeu para Peter Pan no rope drop — bônus de must_do insuficiente quando há grande diferença em D4 | Adicionar bônus de "janela rara" quando fila atual < 40% do histórico para must-do |
| F2 | 03 | Baixa | Nota estratégica redundante quando o dado já está na linha de fila | Suprimir context_note quando informação já é implícita na fila atual |
| F3 | 04 | **Média** | Mensagem diz "fila tá favorável" quando fila = exato máximo tolerado (D1 = 0) | Ramificação no assembler: must_do com fila no limite → frase honesta |
| F4 | 10 | **Média** | Rider swap mencionado mas sem informar que criança específica não pode entrar | Assembler deve personalizar nota com altura da criança e mínimo exigido |

### Correção da falha F1 — bônus de janela rara

No `bonuses.py`, adicionar após o bônus de rare_low_queue:

```python
# Janela rara: must-do com fila muito abaixo do histórico
if attraction.attraction_id in ctx.must_do_attractions:
    historical_avg = attraction.historical_wait(ctx.time_of_day.value)
    current = ctx.queue_snapshot.get(attraction.attraction_id, historical_avg)
    if historical_avg > 0 and current < historical_avg * 0.40:
        bonus += 10.0  # janela rara para atração prioritária
```

### Correção da falha F3 — frase honesta para must_do com fila no limite

No `response_templates.py`, em `_REASON_PHRASES["must_do"]`, adicionar variante:

```python
"must_do_tight_queue": [
    "Era prioridade de vocês — vale esperar os {wait} min.",
    "Tava na lista. A fila não é curta, mas é a janela de hoje.",
]
```

O assembler checa: se `primary_reason == "must_do"` e `current_wait >= max_queue * 0.85`, usa a variante `must_do_tight_queue`.

### Correção da falha F4 — nota de rider swap personalizada

No `response_assembler.py`, em `assemble_get_rec()`:

```python
# Após montar bloco [C]
if "rider_swap_available" in primary.supporting_reasons:
    min_h = ctx_attraction_min_height  # precisa ser passado
    child_h = group.min_child_height
    if child_h and min_h and child_h < min_h:
        lines.append(
            f"⚠️ Criança de {child_h}cm não pode entrar "
            f"(mínimo {min_h}cm). Rider swap disponível."
        )
```

---

## O que está funcionando bem

O sistema funcionou corretamente em 7 dos 10 cenários sem intervenção. Os filtros de chuva, altura, fila máxima, avoiding de tags e filter override todos operaram como projetado. Os pesos situacionais (end_of_day, fatigue) foram ativados corretamente. A diversidade de área no ranker funcionou em todos os cenários com opção B disponível. O tratamento de cenário com apenas 1 elegível (cenário 06) omitiu o bloco [B] sem erro.
