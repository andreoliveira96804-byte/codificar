# Relatório do backtest — venda de puts em ações grandes (esqueleto da estratégia da Annie)

Vende 1 put por ação por semana (delta ≈ −0,25, ~35 dias), recompra com 50% de lucro ou leva ao vencimento. Dados de fim de dia do DoltHub. Comissão de US$ 0,65 por contrato; k = fração do spread paga em cada execução. Não testa a parte discricionária (fluxo de baleias, GEX, Bookmap).

## 1. Universo e operações

100 ações: AAPL, NVDA, MSFT, PFE, V, BAC, MRK, INTC, JPM, MA, QCOM, F, MU, UNH, JNJ, C, HD, XOM, WFC, WMT, T, CVX, AVGO, AMAT, COST, PG, VZ, CSCO, GS, KO, INTU, CMCSA, NKE, ORCL, SBUX, MS, DHR, TMO, LRCX, BMY, TGT, ABT, ABBV, TXN, MDT, IBM, ACN, PEP, LOW, LLY, ATVI, MCD, GE, AXP, UNP, FCX, NEE, CAT, SPGI, AMGN, COP, ADI, FDX, HON, UPS, DE, X, GILD, EBAY, LMT, O, OXY, CERN, CVS, AMT, LIN, BLK, TJX, AA, MMM, NXPI, KLAC, PM, XLNX, M, COF, CSX, SCHW, DVN, FIS, ANTM, MPC, MDLZ, RTX, VIAC, EL, CI, SHW, EQIX, MO.

| Como a put terminou | Puts | % |
|---|---|---|
| recomprada no alvo de 50% | 13.859 | 65% |
| virou pó no vencimento | 3.657 | 17% |
| exercida (ação abaixo do strike) | 3.455 | 16% |
| ainda aberta (fora da análise) | 289 | 1% |

Período: 03/01/2022 a 25/09/2026. Medianas na entrada: 25 dias até o vencimento, strike 5.4% abaixo da ação, prêmio de 1.38% do strike, spread de 12.7% do preço da put. Cotações diárias estimadas pelo sorriso de volatilidade: 31%.

## 2. Resultado por operação (retorno sobre o strike, o capital travado)

- A (exercida: vende a ação no vencimento)
- B (exercida: fica com a ação)
- "Ação no mesmo período": quanto a própria ação rendeu entre a entrada e a saída da put (a referência: vender put tem que valer mais do que simplesmente ter a ação).
- "Anualizado": retorno médio ÷ dias médios × 365 (aproximação simples).

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior | Dias | Anualizado | Ação no mesmo período | Ação anualizada |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Variante A, k=0 (preço médio) | 20971 | +0.3% | +0.9% | 3% | 86% | -5% | -36% | 16 | +6.1% | +0.6% | +14.0% |
| Variante B, k=0 (preço médio) | 20971 | +0.8% | +1.1% | 4% | 97% | +0% | -51% | 26 | +11.8% | +1.1% | +16.3% |
| Variante A, k=0.5 (meio spread) | 20971 | +0.1% | +0.8% | 3% | 86% | -5% | -36% | 16 | +3.0% | +0.6% | +14.0% |
| Variante B, k=0.5 (meio spread) | 20971 | +0.7% | +0.9% | 4% | 97% | +0% | -51% | 26 | +9.8% | +1.1% | +16.3% |
| Variante A, k=1 (spread inteiro) | 20971 | -0.0% | +0.7% | 3% | 82% | -5% | -36% | 16 | -0.1% | +0.6% | +14.0% |
| Variante B, k=1 (spread inteiro) | 20971 | +0.6% | +0.8% | 4% | 93% | -0% | -51% | 26 | +7.8% | +1.1% | +16.3% |

## 3. Decis (variante A, k = 0,5)

Se "IV alta" ajuda, o retorno deve melhorar nos decis de cima.

### IV rank (onde a IV de hoje está entre a mínima e a máxima de 1 ano)

| Decil | Faixa | n | Média | Acerto | Exercidas | Ação no mesmo período |
|---|---|---|---|---|---|---|
| 1 | 0.0000 a 0.0973 | 1975 | -0.19% | 82% | 21% | -0.13% |
| 2 | 0.0973 a 0.16 | 1975 | +0.04% | 85% | 18% | +0.22% |
| 3 | 0.16 a 0.23 | 1974 | +0.08% | 86% | 16% | +0.48% |
| 4 | 0.23 a 0.29 | 1975 | +0.11% | 86% | 15% | +0.65% |
| 5 | 0.29 a 0.36 | 1974 | +0.08% | 85% | 18% | +0.45% |
| 6 | 0.36 a 0.43 | 1975 | +0.05% | 85% | 18% | +0.35% |
| 7 | 0.43 a 0.51 | 1974 | +0.05% | 85% | 17% | +0.48% |
| 8 | 0.51 a 0.62 | 1975 | +0.11% | 86% | 17% | +0.44% |
| 9 | 0.62 a 0.77 | 1974 | +0.51% | 88% | 14% | +1.65% |
| 10 | 0.77 a 1.00 | 1975 | +0.43% | 88% | 14% | +1.29% |

### IV ÷ volatilidade histórica (HV)

| Decil | Faixa | n | Média | Acerto | Exercidas | Ação no mesmo período |
|---|---|---|---|---|---|---|
| 1 | 0.0987 a 0.74 | 1993 | -0.05% | 84% | 18% | +0.23% |
| 2 | 0.74 a 0.85 | 1993 | +0.00% | 84% | 19% | +0.03% |
| 3 | 0.85 a 0.93 | 1993 | +0.03% | 85% | 18% | +0.23% |
| 4 | 0.93 a 1.00 | 1993 | +0.27% | 87% | 15% | +0.81% |
| 5 | 1.00 a 1.07 | 1993 | +0.20% | 86% | 16% | +0.71% |
| 6 | 1.07 a 1.15 | 1993 | +0.19% | 86% | 16% | +0.81% |
| 7 | 1.15 a 1.23 | 1993 | +0.20% | 87% | 15% | +0.91% |
| 8 | 1.23 a 1.35 | 1993 | +0.21% | 87% | 15% | +0.94% |
| 9 | 1.35 a 1.52 | 1993 | +0.10% | 85% | 17% | +0.69% |
| 10 | 1.52 a 4.14 | 1993 | +0.15% | 85% | 18% | +0.56% |

## 4. Por ano (k = 0,5)

2022 foi um ano de queda forte (bear market); 2023–2025, de alta.

| Ano | Puts | Média A | Acerto A | Média B | Exercidas | Ação no mesmo período |
|---|---|---|---|---|---|---|
| 2022 | 4799 | -0.00% | 83% | +0.73% | 20% | +0.00% |
| 2023 | 4273 | +0.14% | 85% | +0.72% | 18% | +0.36% |
| 2024 | 4195 | +0.10% | 86% | +0.49% | 16% | +0.60% |
| 2025 | 4552 | +0.30% | 89% | +0.85% | 13% | +1.25% |
| 2026 | 3152 | +0.13% | 87% | +0.64% | 14% | +1.05% |

## 5. Filtro de IV alta, com teste fora da amostra (variante A, k = 0,5)

Limite = terço mais alto do IV rank no TREINO (entradas antes de 06/05/2024), aplicado congelado no TESTE.

|  | n | Média | Mediana | Desvio | Acerto | 5% piores até | Pior | Ação no mesmo período |
|---|---|---|---|---|---|---|---|---|
| Treino — todas | 10476 | +0.1% | +0.8% | 3% | 84% | -6% | -28% | +0.24% |
| Treino — IV rank ≥ 0.49 | 3257 | +0.5% | +1.1% | 3% | 88% | -5% | -28% | +1.10% |
| Teste (fora da amostra) — todas | 10495 | +0.2% | +0.7% | 3% | 87% | -5% | -36% | +1.00% |
| Teste (fora da amostra) — IV rank ≥ 0.49 | 3142 | +0.2% | +0.9% | 3% | 87% | -6% | -36% | +1.06% |

## 6. Carteira (US$ 100.000, avaliada a mercado toda semana, k = 0,5)

Cada put nova usa 5% do patrimônio como garantia (o tamanho que ela diz usar), sem passar de 100% (sem margem). Com mais candidatas que espaço, entram as de IV rank mais alta; uma posição por ação. Não inclui juros sobre o caixa de garantia (favoreceria as puts) nem dividendos (favoreceriam comprar e segurar).

| Carteira | Capital final | CAGR | Queda máxima | Volatilidade | Sharpe | 2022 |
|---|---|---|---|---|---|---|
| Puts — variante A, todas | US$ 106.513 | +1.3% | -8% | 6% | 0.24 | -3% |
| Puts — variante A, só IV rank ≥ 0.49 | US$ 104.291 | +0.9% | -7% | 6% | 0.20 | -1% |
| Puts — variante B, todas (fica com a ação) | US$ 120.349 | +4.0% | -14% | 10% | 0.44 | -5% |
| Comprar e segurar as mesmas ações (pesos iguais) | US$ 167.919 | +11.6% | -19% | 15% | 0.82 | -8% |
| Comprar e segurar o SPY | US$ 161.918 | +10.8% | -25% | 17% | 0.70 | -20% |
