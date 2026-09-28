# Relatório do backtest — venda de puts em ações grandes (esqueleto da estratégia da Annie)

Vende 1 put por ação por semana (delta ≈ −0,25, ~35 dias), recompra com 50% de lucro ou leva ao vencimento. Dados de fim de dia do DoltHub. Comissão de US$ 0,65 por contrato; k = fração do spread paga em cada execução. Não testa a parte discricionária (fluxo de baleias, GEX, Bookmap).

## 1. Universo e operações

100 ações: AAPL, NVDA, MSFT, PFE, V, BAC, MRK, INTC, JPM, MA, QCOM, F, MU, UNH, JNJ, C, HD, XOM, WFC, WMT, T, CVX, AVGO, AMAT, COST, PG, VZ, CSCO, GS, KO, INTU, CMCSA, NKE, ORCL, SBUX, MS, DHR, TMO, LRCX, BMY, TGT, ABT, ABBV, TXN, MDT, IBM, ACN, PEP, LOW, LLY, ATVI, MCD, GE, AXP, UNP, FCX, NEE, CAT, SPGI, AMGN, COP, ADI, FDX, HON, UPS, DE, X, GILD, EBAY, LMT, O, OXY, CERN, CVS, AMT, LIN, BLK, TJX, AA, MMM, NXPI, KLAC, PM, XLNX, M, COF, CSX, SCHW, DVN, FIS, ANTM, MPC, MDLZ, RTX, VIAC, EL, CI, SHW, EQIX, MO.

| Como a put terminou | Puts | % |
|---|---|---|
| recomprada no alvo de 50% | 13.847 | 65% |
| virou pó no vencimento | 3.655 | 17% |
| exercida (ação abaixo do strike) | 3.455 | 16% |
| ainda aberta (fora da análise) | 289 | 1% |

Período: 03/01/2022 a 25/09/2026. Medianas na entrada: 25 dias até o vencimento, strike 5.4% abaixo da ação, prêmio de 1.38% do strike, spread de 12.8% do preço da put. Cotações diárias estimadas pelo sorriso de volatilidade: 31%.

## 2. Resultado por operação (retorno sobre o strike, o capital travado)

- A (exercida: vende a ação no vencimento)
- B (exercida: fica com a ação)
- "Ação no mesmo período": quanto a própria ação rendeu entre a entrada e a saída da put (a referência: vender put tem que valer mais do que simplesmente ter a ação).
- "Anualizado": retorno médio ÷ dias médios × 365 (aproximação simples).

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior | Dias | Anualizado | Ação no mesmo período | Ação anualizada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Variante A, k=0 (preço médio) | 20957 | +0.3% | +0.9% | 3% | 86% | -5% | -89% | 16 | +5.8% | +0.6% | +13.7% |
| Variante B, k=0 (preço médio) | 20957 | +0.8% | +1.1% | 4% | 97% | +0% | -90% | 26 | +11.3% | +1.1% | +15.8% |
| Variante A, k=0.5 (meio spread) | 20957 | +0.1% | +0.8% | 3% | 86% | -5% | -89% | 16 | +2.7% | +0.6% | +13.7% |
| Variante B, k=0.5 (meio spread) | 20957 | +0.7% | +0.9% | 4% | 97% | +0% | -90% | 26 | +9.3% | +1.1% | +15.8% |
| Variante A, k=1 (spread inteiro) | 20957 | -0.0% | +0.7% | 3% | 82% | -5% | -90% | 16 | -0.5% | +0.6% | +13.7% |
| Variante B, k=1 (spread inteiro) | 20957 | +0.5% | +0.8% | 4% | 93% | -0% | -90% | 26 | +7.4% | +1.1% | +15.8% |

## 3. Decis (variante A, k = 0,5)

Se "IV alta" ajuda, o retorno deve melhorar nos decis de cima.

### IV rank (onde a IV de hoje está entre a mínima e a máxima de 1 ano)

| Decil | Faixa | n | Média | Acerto | Exercidas | Ação no mesmo período |
|---|---|---|---|---|---|---|
| 1 | 0.0000 a 0.0973 | 1974 | -0.19% | 82% | 21% | -0.14% |
| 2 | 0.0974 a 0.16 | 1973 | +0.04% | 85% | 18% | +0.22% |
| 3 | 0.16 a 0.23 | 1973 | +0.08% | 86% | 16% | +0.48% |
| 4 | 0.23 a 0.29 | 1973 | +0.11% | 86% | 15% | +0.66% |
| 5 | 0.29 a 0.36 | 1973 | +0.05% | 85% | 18% | +0.41% |
| 6 | 0.36 a 0.43 | 1973 | +0.05% | 85% | 18% | +0.36% |
| 7 | 0.43 a 0.51 | 1973 | +0.01% | 85% | 17% | +0.43% |
| 8 | 0.51 a 0.62 | 1973 | +0.11% | 86% | 16% | +0.45% |
| 9 | 0.62 a 0.77 | 1973 | +0.46% | 88% | 14% | +1.61% |
| 10 | 0.77 a 1.00 | 1974 | +0.39% | 88% | 14% | +1.24% |

### IV ÷ volatilidade histórica (HV)

| Decil | Faixa | n | Média | Acerto | Exercidas | Ação no mesmo período |
|---|---|---|---|---|---|---|
| 1 | 0.0987 a 0.74 | 1992 | -0.05% | 84% | 18% | +0.23% |
| 2 | 0.74 a 0.85 | 1992 | -0.04% | 84% | 19% | -0.01% |
| 3 | 0.85 a 0.93 | 1991 | -0.01% | 85% | 18% | +0.19% |
| 4 | 0.93 a 1.00 | 1992 | +0.27% | 87% | 15% | +0.80% |
| 5 | 1.00 a 1.07 | 1991 | +0.16% | 86% | 16% | +0.66% |
| 6 | 1.07 a 1.15 | 1992 | +0.14% | 86% | 16% | +0.76% |
| 7 | 1.15 a 1.23 | 1991 | +0.20% | 87% | 15% | +0.91% |
| 8 | 1.23 a 1.35 | 1992 | +0.21% | 87% | 15% | +0.94% |
| 9 | 1.35 a 1.52 | 1991 | +0.11% | 85% | 17% | +0.70% |
| 10 | 1.52 a 4.14 | 1992 | +0.15% | 85% | 18% | +0.57% |

## 4. Por ano (k = 0,5)

2022 foi um ano de queda forte (bear market); 2023–2025, de alta.

| Ano | Puts | Média A | Acerto A | Média B | Exercidas | Ação no mesmo período |
|---|---|---|---|---|---|---|
| 2022 | 4799 | -0.00% | 83% | +0.73% | 20% | +0.00% |
| 2023 | 4259 | +0.14% | 85% | +0.72% | 18% | +0.37% |
| 2024 | 4195 | +0.04% | 86% | +0.35% | 17% | +0.53% |
| 2025 | 4552 | +0.30% | 89% | +0.85% | 13% | +1.25% |
| 2026 | 3152 | +0.11% | 87% | +0.61% | 14% | +1.02% |

## 5. Filtro de IV alta, com teste fora da amostra (variante A, k = 0,5)

Limite = terço mais alto do IV rank no TREINO (entradas antes de 06/05/2024), aplicado congelado no TESTE.

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior | Ação no mesmo período |
|---|---|---|---|---|---|---|---|---|
| Treino — todas | 10462 | +0.1% | +0.8% | 3% | 84% | -6% | -28% | +0.25% |
| Treino — IV rank ≥ 0.49 | 3253 | +0.5% | +1.1% | 3% | 88% | -5% | -28% | +1.10% |
| Teste (fora da amostra) — todas | 10495 | +0.1% | +0.7% | 3% | 87% | -5% | -89% | +0.96% |
| Teste (fora da amostra) — IV rank ≥ 0.49 | 3141 | +0.1% | +0.9% | 4% | 87% | -6% | -88% | +0.99% |

## 6. Carteira (US$ 100.000, avaliada a mercado toda semana, k = 0,5)

Cada put nova usa 5% do patrimônio como garantia (o tamanho que ela diz usar), sem passar de 100% (sem margem). Com mais candidatas que espaço, entram as de IV rank mais alta; uma posição por ação. Não inclui juros sobre o caixa de garantia (favoreceria as puts) nem dividendos (favoreceriam comprar e segurar).

| Carteira | Capital final | CAGR | Queda máxima | Volatilidade | Sharpe | 2022 |
|---|---|---|---|---|---|---|
| Puts — variante A, todas | US$ 102.637 | +0.6% | -10% | 7% | 0.12 | -3% |
| Puts — variante A, só IV rank ≥ 0.49 | US$ 99.473 | -0.1% | -8% | 6% | 0.01 | -1% |
| Puts — variante B, todas (fica com a ação) | US$ 114.509 | +2.9% | -14% | 10% | 0.33 | -4% |
| Comprar e segurar as mesmas ações (pesos iguais) | US$ 147.164 | +8.5% | -19% | 14% | 0.65 | -8% |
| Comprar e segurar o SPY | US$ 161.918 | +10.8% | -25% | 17% | 0.70 | -20% |
