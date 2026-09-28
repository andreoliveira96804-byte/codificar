# Backtest: venda de volatilidade em resultados trimestrais

Backtest **aproximado** da estratégia do vídeo: vender a volatilidade implícita
(IV) inflada antes da divulgação de resultados (*earnings*) e lucrar com a queda
dela depois do anúncio (*IV crush*). São testadas duas montagens:

- **Straddle vendido:** vende 1 call + 1 put no dinheiro (ATM), no vencimento curto.
- **Calendar de call comprado:** vende a call ATM do vencimento curto e compra
  a call do mesmo strike com vencimento ~30 dias depois.

Os dados vêm de bases públicas e gratuitas do [DoltHub](https://www.dolthub.com/users/post-no-preference/repositories):
`post-no-preference/options` (cadeias de opções), `post-no-preference/stocks`
(preços das ações) e `post-no-preference/earnings` (calendário de resultados).

## Como rodar

```bash
pip install -r backtest_earnings/requirements.txt

# teste rápido com poucas ações (~2 min)
python -m backtest_earnings.executar --inicio 2024-10-01 --simbolos AAPL,MSFT,AMZN --saida resultados

# backtest completo (1h30–2h na primeira vez; depois usa o cache em dados/cache)
python -m backtest_earnings.executar --inicio 2022-01-01 --saida resultados

# relatório em Markdown (resultados/relatorio.md)
python -m backtest_earnings.relatorio --pasta resultados

# testes automáticos
python -m pytest tests
```

## O que o código faz

1. **Eventos:** pega os resultados com horário conhecido. Eles podem ser
   **AMC** (*After Market Close*, depois do fechamento) ou **BMO**
   (*Before Market Open*, antes da abertura).
2. **Datas:** a entrada é no fechamento do último pregão antes do anúncio e a
   saída no fechamento do primeiro pregão depois dele.
3. **Filtros na entrada** (os 3 do vídeo):
   - `ts_slope_0_45`: inclinação da curva de IV entre o primeiro vencimento e 45 dias.
   - `iv30_rv30`: IV de 30 dias dividida pela volatilidade realizada (RV) de 30 dias,
     calculada pelo estimador de Yang-Zhang.
   - `volume_medio_30`: volume médio da ação nos últimos 30 pregões.
4. **Contratos:**
   - vencimento curto = o primeiro depois da saída;
   - vencimento longo = o mais próximo de curto + 30 dias;
   - strike = o mais próximo do preço da ação.
5. **Retorno com custos:** cada execução paga uma fração `k` do spread, e a
   comissão é de US$ 0,65 por contrato.
   - `k = 0`: executa no preço médio;
   - `k = 0,5`: paga meio spread (é o padrão);
   - `k = 1`: paga o spread inteiro.
6. **Relatório:**
   - resultado sem filtro;
   - decis de cada filtro;
   - filtros com os limites do vídeo;
   - limites recalibrados e **teste fora da amostra**;
   - resultado por ano e retorno acumulado;
   - **Kelly** e **Monte Carlo**, sorteando temporadas inteiras de resultados.

## Limitações (por que é "aproximado")

| Limitação | Efeito |
|---|---|
| Dados de **fim de dia**: a saída é no fechamento, não 15 min após a abertura | A ação tem mais tempo para andar depois do anúncio. O vídeo mostra que isso piora o resultado (deriva pós-resultado, ou PEAD). |
| A base só guarda **~3 vencimentos por dia**, e o primeiro fica a ~2 semanas | A queda da IV depois do resultado é menor que no vencimento de poucos dias do vídeo. A escala da inclinação muda, então os limites do vídeo não se aplicam diretamente. |
| Só **~20 strikes por vencimento**, e eles mudam de um dia para o outro | Quando o strike some, o preço é **estimado** por Black-Scholes com o sorriso de volatilidade do dia. O CSV marca essas pernas com as colunas `*_est_*`. No teste de validação, o erro mediano foi de ~2% do preço, menos de meio spread. |
| Antes de ~set/2024 a base de opções só tem **segundas, quartas e sextas** | Nesse período, a entrada pode ser antecipada e a saída adiada em até 2 pregões. As colunas `defasagem_entrada` e `defasagem_saida` registram isso, e `exato` indica se não houve defasagem. |
| Sem dividendos e sem exercício antecipado | Pequeno efeito para prazos curtos. |

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `dolthub.py` | Cliente da API SQL do DoltHub: cache em disco, paralelismo e limite de 1.000 linhas por consulta |
| `eventos.py` | Calendário de pregões, calendário de resultados e datas de entrada/saída |
| `indicadores.py` | Yang-Zhang, sorriso de volatilidade, estrutura a termo e os 3 filtros |
| `estrategias.py` | Escolha dos contratos, cotação (real ou estimada), Black-Scholes e retornos |
| `analise.py` | Resumo, decis, classes do scanner, Kelly e Monte Carlo |
| `executar.py` | Programa principal: baixa os dados e gera `trades.csv` |
| `relatorio.py` | Gera `relatorio.md` a partir de `trades.csv` |
