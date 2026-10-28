# Contrato de decisões do recurso

`output/decisoes_recurso.json` é um rascunho local produzido pelo painel ou pelo comando
`python scripts/recurso_glosa.py template`.

## Cabeçalho

- `sequencial_transacao`: identificador numérico, máximo 12 dígitos.
- `numero_lote_recurso`: lote numérico novo, diferente do lote original.
- `numero_guia_rec_glosa_prestador`: campo confirmado pelo analista para a tag homônima.
- `numero_guia_rec_glosa_operadora`: campo confirmado pelo analista para a tag homônima.
- `numero_guia_origem`: campo confirmado pelo analista para a tag homônima.
- `numero_guia_operadora`: campo confirmado pelo analista para a tag homônima.
- `guias_confirmadas_manualmente`: deve ser literalmente `true` após conferir as colunas
  J/K do demonstrativo visual da CAPESESP.
- `data_recurso`: data em `YYYY-MM-DD`.

Os valores sugeridos pelo template seguem as setas do manual da CAPESESP, mas não são
considerados confirmados automaticamente.

## Itens

Deve existir exatamente uma decisão para cada item do contrato:

```json
{
  "sequencialItem": 23,
  "decisao": "RECORRER",
  "valor_recursado": "62.04",
  "justificativa": "Cobrança conforme contrato e documentação anexa",
  "confirmacao_manual_provavel": false
}
```

`decisao` aceita `RECORRER`, `ACEITAR_GLOSA` ou `AGUARDAR_DOCUMENTACAO`. O campo
`confirmacao_manual_provavel` precisa ser `true` para recorrer um item `PROVAVEL`.
Valores são strings decimais com no máximo duas casas. A justificativa é obrigatória para
recurso e tem limite ponderado CAPESESP de 150: letras/números ASCII e espaço valem um;
acentos, pontuação e demais caracteres valem dois. Caracteres fora de ISO-8859-1 são
rejeitados.

## Estados operacionais

- Salvar decisões: rascunho editável.
- Gerar XML: validação/dry-run repetível, sem transmissão.
- `mark-sent`: registro humano posterior ao upload manual; bloqueia novas gerações para o
  protocolo no registro SQLite local.
