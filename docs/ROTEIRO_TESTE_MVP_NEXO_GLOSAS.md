# Roteiro de teste MVP — Nexo Glosas

Sessão sugerida: 30 a 45 minutos, com a equipe de Recurso de Glosas. O teste é local e não envia dados
automaticamente ao MV ou à operadora.

## Papéis durante o teste

- **Operadora:** navega, pesquisa o código e registra a decisão.
- **Revisora:** confere guia, documentos, valor e justificativa.
- **Observador:** anota dúvidas, mensagens e pontos de melhoria.

Troquem Operadora e Revisora na metade da sessão para validar se o fluxo é compreensível
para mais de uma pessoa.

## Pré-condição do teste de foco

O XML usado no teste precisa conter ao menos um código de um destes grupos TISS/MV:

- Honorários: `2601` a `2699`;
- OPME: `2201` a `2299`;
- Diárias: `1901` a `1999`;
- Taxas e aluguéis: `2401` a `2499`.

O protocolo inicialmente carregado no projeto não possui itens desses grupos. Ele pode validar
o funcionamento geral, mas não deve ser apresentado como amostra representativa do foco.

## Cenários mínimos

1. Abrir **Dicionário de glosas** e testar um código de cada linha: `2603` (honorários),
   `2209` (OPME), `1914` (diárias) e `2418` (taxas).
2. Conferir descrição, características, documentos e texto-base de cada linha.
3. Abrir **Análise de glosas**, filtrar cada linha de foco e clicar no código para voltar
   diretamente à ficha do dicionário.
4. Selecionar somente um item confirmado para **Recorrer**.
5. Conferir o valor e redigir a justificativa com base na evidência real. O texto-base é
   apenas ponto de partida e não deve ser usado sem revisão.
6. Abrir **Montar recurso**, revisar o checklist e confirmar manualmente as guias somente
   depois de comparar as colunas J/K do demonstrativo.
7. Gerar o XML em dry-run. Não fazer upload durante o primeiro teste.
8. Abrir **Indicadores & BI** e baixar o CSV consolidado.

## Resultado esperado

- Os 64 códigos priorizados estão disponíveis: 10 de honorários, 12 de OPME, 17 de
  diárias e 25 de taxas.
- A busca funciona por código, descrição, grupo e característica.
- O código exibido na análise abre diretamente sua ficha no dicionário.
- Nenhuma decisão é tomada automaticamente pelo sistema.
- Um item provável não pode ser recursado sem confirmação manual.
- O XML só é gerado quando valor, justificativa e identificação estão válidos.
- O CSV contém código da glosa, decisão, valores e origem da conciliação.

## Evidências a registrar

- Print da ficha do código consultado.
- Código e item usados no teste, sem dado de paciente no registro da reunião.
- Dúvidas sobre descrição, documentos ou responsável sugerido.
- Mensagem completa de qualquer erro.
- Resultado da validação do XML e abertura do CSV.

## Regra de parada

Se o fluxo indicar envio, baixa, aceite financeiro ou alteração no MV, interromper o teste.
Essas ações não pertencem ao primeiro MVP e exigem validação específica em homologação.
