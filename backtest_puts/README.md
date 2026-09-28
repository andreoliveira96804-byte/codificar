# Backtest: venda de puts em ações grandes

Testa o **esqueleto** da estratégia apresentada pela Annie no podcast
*Undiscovered Traders*: vender puts fora do dinheiro (OTM) em ações grandes que
pagam dividendo, preferindo volatilidade implícita (IV) alta, e realizar o lucro
rápido. Se a put for exercida, ela fica com a ação ("vira investidora").

**Não testa** a parte discricionária e paga da estratégia: fluxo de "baleias"
(dark pool, sweeps), níveis de gamma (GEX, put wall / call wall), GARCH rank e o
Bookmap. Para essas partes seriam necessários dados históricos pagos, como
*open interest* por strike e negócios de opções.

## Regras

| Item | Regra |
|---|---|
| Universo | As 100 ações mais negociadas em US$ no trimestre anterior ao início, que pagaram dividendo no ano anterior, não são ETF e têm opções na base. Só usa dados de **antes** do teste, então não há viés de sobrevivência. |
| Entrada | Uma put por ação por semana, no primeiro dia da semana com dados. Vencimento mais perto de 35 dias (entre 21 e 56); delta mais perto de −0,25 (entre −0,20 e −0,30). |
| Saída | Recompra quando o preço médio da put cai à metade (50% do prêmio embolsado). Senão, vai até o vencimento. |
| Exercida, variante A | Vende a ação no vencimento e realiza o prejuízo. |
| Exercida, variante B | Fica com a ação até ela voltar ao strike, por no máximo 126 pregões (~6 meses). |
| Custos | Meio spread por execução (k = 0,5) e US$ 0,65 por contrato. |
| Carteira | US$ 100 mil. Cada put usa 5% do patrimônio como garantia, sem margem, uma posição por ação. Avaliada a mercado toda semana. |

## Como rodar

```bash
python -m backtest_puts.executar --inicio 2022-01-01 --saida resultados_puts   # ~1h na primeira vez
python -m backtest_puts.relatorio --pasta resultados_puts
```

## Limitações

- **A base só mostra cada vencimento até ~11 dias antes de vencer.** Nessa reta
  final o alvo de 50% não é conferido. O resultado no vencimento é exato, porque
  a put vale max(strike − ação, 0). Para avaliar a carteira nesses dias, usa-se
  o valor intrínseco.
- **Dados de fim de dia.** Ela sai no mesmo dia, em minutos ou horas; aqui o alvo
  só é conferido no fechamento.
- **Strikes que somem.** A base guarda ~20 strikes por vencimento, e eles mudam
  todo dia. As cotações que faltam são estimadas por Black-Scholes com o sorriso
  de volatilidade do dia (ver `backtest_earnings/estrategias.py`).
- **O que fica de fora.** Não inclui os juros sobre o caixa de garantia, o que
  favoreceria as puts, nem os dividendos das ações, o que favoreceria comprar e
  segurar.
