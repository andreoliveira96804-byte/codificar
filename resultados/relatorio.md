# Relatório do backtest — venda de volatilidade em resultados

Backtest APROXIMADO com dados de fim de dia (EOD) do DoltHub: entrada no fechamento antes do anúncio, saída no fechamento depois dele. k = fração do spread paga em cada execução; comissão de US$ 0,65 por contrato. Retorno do straddle sobre o prêmio recebido; do calendar sobre o débito pago.

## 1. Funil de eventos

| Etapa | Eventos |
|---|---|
| eventos com horário (AMC/BMO) | 64.153 |
| com dia de opções na entrada e na saída | 62.007 |
| com cadeia de opções na entrada | 24.955 |
| com preços e contratos montáveis | 24.211 |
| straddle com cotações válidas | 21.836 |
| calendar com cotações válidas | 21.168 |

Período: 03/01/2022 a 25/09/2026. Operações com datas exatas (sem defasagem): 47%. Primeiro vencimento disponível: mediana de 16 dias.

Pernas com preço ESTIMADO (Black-Scholes pelo sorriso do dia) em algum momento: call curta 7%, put curta 7%, call longa 14%.

## 2. Liquidez das opções (k = 0,5)

Spread do straddle na entrada = (soma dos ask − soma dos bid) ÷ preço médio do straddle. Opções ilíquidas têm cotações pouco confiáveis e custo de execução altíssimo.

| Spread na entrada | n straddle | Média | Mediana | Acerto | n calendar | Média | Mediana | Acerto | Volume mediano da ação |
|---|---|---|---|---|---|---|---|---|---|
| até 2% | 23 | +0.5% | +13.4% | 74% | 21 | -3.7% | -0.1% | 48% | 24.39 mi |
| 2% a 5% | 589 | -2.3% | +8.1% | 61% | 497 | -28.7% | -16.0% | 26% | 4.32 mi |
| 5% a 10% | 3054 | -9.7% | +4.6% | 56% | 2827 | -36.9% | -25.7% | 17% | 1.69 mi |
| 10% a 20% | 4763 | -14.2% | -0.0% | 50% | 4403 | -50.1% | -39.3% | 9% | 1.41 mi |
| 20% a 40% | 4850 | -25.6% | -9.2% | 38% | 4506 | -69.6% | -61.9% | 4% | 0.96 mi |
| acima de 40% | 8557 | -78.5% | -58.4% | 14% | 7354 | -106.7% | -100.2% | 1% | 0.51 mi |

**Universo negociável** (usado da seção 4 em diante): spread do straddle na entrada até 10%. Esse limite foi escolhido depois de ver esta tabela; é a regra prática de não operar opções com spread largo, e só usa informação disponível na entrada.

## 3. Sem os filtros do vídeo

No vídeo, operar todos os eventos dá retorno médio perto de zero.

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior |
|---|---|---|---|---|---|---|---|
| Todos — Straddle vendido, k=0 (preço médio) | 21836 | -7.4% | +5.9% | 49% | 57% | -103% | -568% |
| Todos — Straddle vendido, k=0.5 (meio spread) | 21836 | -41.0% | -18.4% | 75% | 34% | -185% | -980% |
| Todos — Straddle vendido, k=1 (spread inteiro) | 21836 | -176.9% | -44.3% | 652% | 23% | -631% | -21726% |
| Todos — Calendar, k=0 (preço médio) | 19608 | +1.4% | -2.1% | 103% | 47% | -103% | -1017% |
| Todos — Calendar, k=0.5 (meio spread) | 19608 | -73.3% | -66.3% | 64% | 7% | -177% | -1180% |
| Todos — Calendar, k=1 (spread inteiro) | 19608 | -102.3% | -95.1% | 70% | 1% | -206% | -1579% |
| Negociável — Straddle vendido, k=0 (preço médio) | 3666 | -2.7% | +10.2% | 45% | 62% | -93% | -378% |
| Negociável — Straddle vendido, k=0.5 (meio spread) | 3666 | -8.4% | +5.2% | 47% | 57% | -104% | -392% |
| Negociável — Straddle vendido, k=1 (spread inteiro) | 3666 | -14.4% | +0.6% | 50% | 51% | -116% | -407% |
| Negociável — Calendar, k=0 (preço médio) | 3345 | -2.0% | +2.2% | 51% | 52% | -83% | -543% |
| Negociável — Calendar, k=0.5 (meio spread) | 3345 | -35.4% | -24.2% | 52% | 18% | -114% | -653% |
| Negociável — Calendar, k=1 (spread inteiro) | 3345 | -59.6% | -45.3% | 66% | 5% | -162% | -982% |

## 4. Decis (k = 0,5)

Cada variável dividida em 10 grupos do mesmo tamanho (1 = menores valores). Se o filtro funciona, o retorno deve melhorar de forma consistente numa direção.

### Inclinação da estrutura a termo (0→45 dias)

| Decil | Faixa | n | Straddle média | Straddle acerto | Calendar média | Calendar acerto |
|---|---|---|---|---|---|---|
| 1 | -0.0726 a -0.0081 | 367 | -7.4% | 58% | -41.5% | 26% |
| 2 | -0.0081 a -0.0056 | 367 | -5.0% | 60% | -38.3% | 26% |
| 3 | -0.0056 a -0.0045 | 366 | -8.1% | 59% | -35.4% | 23% |
| 4 | -0.0045 a -0.0036 | 367 | -10.1% | 56% | -37.8% | 22% |
| 5 | -0.0036 a -0.0029 | 366 | -8.4% | 57% | -40.2% | 21% |
| 6 | -0.0029 a -0.0024 | 367 | -7.9% | 59% | -33.1% | 21% |
| 7 | -0.0024 a -0.0019 | 366 | -12.5% | 53% | -33.7% | 16% |
| 8 | -0.0018 a -0.0014 | 367 | -10.6% | 52% | -34.7% | 11% |
| 9 | -0.0014 a -0.0010 | 366 | -5.9% | 58% | -29.6% | 12% |
| 10 | -0.0010 a 0.0234 | 367 | -8.4% | 58% | -30.0% | 5% |

### IV30 / RV30

| Decil | Faixa | n | Straddle média | Straddle acerto | Calendar média | Calendar acerto |
|---|---|---|---|---|---|---|
| 1 | 0.0733 a 1.03 | 367 | -3.0% | 59% | -24.4% | 17% |
| 2 | 1.03 a 1.14 | 366 | -8.3% | 58% | -27.2% | 9% |
| 3 | 1.14 a 1.23 | 367 | -5.7% | 61% | -30.4% | 14% |
| 4 | 1.23 a 1.30 | 366 | -8.8% | 57% | -33.7% | 16% |
| 5 | 1.30 a 1.37 | 367 | -7.7% | 57% | -34.0% | 19% |
| 6 | 1.37 a 1.45 | 366 | -12.5% | 54% | -38.9% | 22% |
| 7 | 1.45 a 1.54 | 366 | -11.5% | 54% | -37.0% | 19% |
| 8 | 1.54 a 1.67 | 367 | -7.6% | 56% | -39.2% | 18% |
| 9 | 1.67 a 1.86 | 366 | -7.1% | 58% | -41.0% | 24% |
| 10 | 1.86 a 3.86 | 367 | -12.0% | 57% | -48.3% | 24% |

### Volume médio de 30 dias

| Decil | Faixa | n | Straddle média | Straddle acerto | Calendar média | Calendar acerto |
|---|---|---|---|---|---|---|
| 1 | 63916.30 a 0.44 mi | 367 | -11.0% | 57% | -47.0% | 17% |
| 2 | 0.44 mi a 0.70 mi | 366 | -9.5% | 58% | -39.0% | 19% |
| 3 | 0.71 mi a 1.01 mi | 367 | -13.7% | 53% | -42.7% | 18% |
| 4 | 1.01 mi a 1.32 mi | 366 | -12.2% | 50% | -36.2% | 16% |
| 5 | 1.32 mi a 1.65 mi | 367 | -10.1% | 55% | -38.1% | 19% |
| 6 | 1.65 mi a 2.18 mi | 366 | -7.4% | 59% | -35.5% | 16% |
| 7 | 2.19 mi a 3.18 mi | 366 | -4.7% | 60% | -30.5% | 17% |
| 8 | 3.18 mi a 5.46 mi | 367 | -7.0% | 59% | -32.7% | 19% |
| 9 | 5.47 mi a 10.63 mi | 366 | -2.2% | 63% | -27.3% | 17% |
| 10 | 10.69 mi a 348.08 mi | 367 | -6.3% | 57% | -25.1% | 23% |

## 5. Filtros com os limites do vídeo

Atenção: aqui o primeiro vencimento fica a ~2 semanas (no vídeo, a poucos dias), então a escala da inclinação é diferente e o limite do vídeo não é diretamente comparável.

Limites: volume ≥ 1.50 mi, IV30/RV30 ≥ 1.25, inclinação ≤ -0.00406.

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior |
|---|---|---|---|---|---|---|---|
| Recommended — Straddle vendido | 509 | -6.9% | +9.7% | 58% | 60% | -124% | -331% |
| Recommended — Calendar | 436 | -34.5% | -27.3% | 54% | 25% | -114% | -275% |
| Consider — Straddle vendido | 681 | -9.0% | +7.5% | 55% | 57% | -117% | -392% |
| Consider — Calendar | 644 | -42.4% | -30.4% | 67% | 23% | -135% | -653% |
| Avoid — Straddle vendido | 2476 | -8.6% | +4.5% | 43% | 57% | -96% | -318% |
| Avoid — Calendar | 2265 | -33.6% | -22.3% | 46% | 15% | -106% | -593% |

## 6. Filtros recalibrados e teste fora da amostra

Os limites foram calculados só com o período de TREINO (entradas antes de 24/01/2024) usando quantis fixados antes de ver o resultado: inclinação no terço mais negativo, IV30/RV30 no terço mais alto e volume acima da mediana. Depois foram aplicados, congelados, no período de TESTE.

Limites do treino: volume ≥ 1.92 mi, IV30/RV30 ≥ 1.42, inclinação ≤ -0.00369.

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior |
|---|---|---|---|---|---|---|---|
| Treino — Straddle vendido, todos | 1670 | -7.7% | +4.6% | 44% | 57% | -97% | -318% |
| Treino — Straddle vendido, Recommended | 82 | -0.4% | +8.9% | 46% | 56% | -111% | -142% |
| Treino — Calendar, todos | 1477 | -30.1% | -20.5% | 44% | 18% | -100% | -475% |
| Treino — Calendar, Recommended | 57 | -23.5% | -11.2% | 41% | 30% | -100% | -126% |
| Teste (fora da amostra) — Straddle vendido, todos | 1996 | -9.0% | +5.8% | 50% | 57% | -108% | -392% |
| Teste (fora da amostra) — Straddle vendido, Recommended | 232 | -5.5% | +13.8% | 61% | 63% | -132% | -331% |
| Teste (fora da amostra) — Calendar, todos | 1868 | -39.6% | -29.4% | 57% | 18% | -128% | -653% |
| Teste (fora da amostra) — Calendar, Recommended | 200 | -33.7% | -26.8% | 54% | 26% | -132% | -232% |

## 7. Por ano (k = 0,5; limites recalibrados)

| Ano | n todos | Straddle todos | Calendar todos | n Recommended | Straddle Rec. | Calendar Rec. |
|---|---|---|---|---|---|---|
| 2022 | 793 | -8.6% | -29.7% | 48 | +3.2% | -26.1% |
| 2023 | 1510 | -7.5% | -30.1% | 119 | -2.3% | -22.7% |
| 2024 | 1367 | -12.3% | -41.1% | 152 | -3.9% | -26.1% |
| 2025 | 804 | -4.0% | -36.6% | 119 | -8.5% | -36.0% |
| 2026 | 274 | -8.7% | -42.1% | 49 | -0.3% | -43.8% |

## 8. Retorno acumulado (US$ 10.000, 5% do capital por dia de operação, k = 0,5)

Quando várias operações entram no mesmo dia, o capital daquele dia é dividido igualmente entre elas (usamos o retorno médio do dia).

| Carteira | Dias com operação | Capital final | Retorno | Queda máxima |
|---|---|---|---|---|
| Todos — Straddle vendido | 584 | US$ 798 | -92% | -92% |
| Todos — Calendar | 572 | US$ 0 | -100% | -100% |
| Recommended — Straddle vendido | 200 | US$ 7.532 | -25% | -43% |
| Recommended — Calendar | 172 | US$ 624 | -94% | -94% |

## 9. Kelly e Monte Carlo (Recommended, período de teste, k = 0,5)

Monte Carlo: 10.000 caminhos de 1 ano, começando com US$ 10.000. Sorteamos TEMPORADAS inteiras de resultados (e não operações soltas), para que perdas que acontecem juntas continuem juntas. Obs.: a simulação faz uma operação de cada vez; na prática várias ficam abertas juntas, o que aumenta o risco.

| Estratégia | Tamanho | % do capital por operação | Operações/ano | Capital mediano | 5% piores | Prob. prejuízo | Prob. quebra (−95%) | Queda máx. mediana |
|---|---|---|---|---|---|---|---|---|
| Straddle vendido | Kelly cheio | 0% (média ≤ 0: não apostar) | — | — | — | — | — | — |
| Straddle vendido | 1/4 Kelly | 0% (média ≤ 0: não apostar) | — | — | — | — | — | — |
| Straddle vendido | 1/10 Kelly | 0% (média ≤ 0: não apostar) | — | — | — | — | — | — |
| Calendar | Kelly cheio | 0% (média ≤ 0: não apostar) | — | — | — | — | — | — |
| Calendar | 1/4 Kelly | 0% (média ≤ 0: não apostar) | — | — | — | — | — | — |
| Calendar | 1/10 Kelly | 0% (média ≤ 0: não apostar) | — | — | — | — | — | — |
