# Guia de teste — tela "Glosa por Procedimento" (Recurso de Glosa CAPESESP)

Documento de apoio para a sessão de teste com a equipe de Recurso de Glosas. Caso real
usado como piloto (identificadores anonimizados neste documento público): convênio CAPE
SAÚDE, conta/guia **100000**, protocolo **00000001**, lote **9001**.

## O que já está pronto

- Acesso liberado para os dois usuários-piloto do setor (matrículas internas).
- 3 itens de teste já cadastrados na conta 100000, visíveis na tela, com motivo e
  observação preenchidos — servem só pra vocês praticarem, **não são recurso real**:

| Procedimento | Descrição | Valor glosado | Motivo cadastrado |
|---|---|---|---|
| `08020760` | EQUIPO MACROGOTAS FLEXIVEL EV-HART AIR | R$ 62,04 | MAT/MED INCOMPATÍVEIS |
| `07020468` | ALLEGRA | R$ 3,59 | MAT/MED INCOMPATÍVEIS |
| `08012765` | COMPRESSA GAZE 7,5CM X 7,5CM 13F | R$ 21,08 | MAT/MED INCOMPATÍVEIS |

Esses 3 têm a palavra **"TESTE PILOTO"** no campo Observação — é assim que vocês
reconhecem que são de teste.

## O que ainda NÃO foi testado (é isso que precisamos descobrir juntos)

Ninguém clicou ainda em "Ent. Recurso" nem em "Entr. Rec. Recurso". Não sabemos o que
essas telas pedem, nem se geram um XML, nem se enviam alguma coisa de verdade. **Por
isso o teste de hoje é só nos 3 itens marcados "TESTE PILOTO"** — nunca nos itens reais
da conta (as outras linhas em vermelho, que são glosas financeiras de verdade, já
existentes no sistema).

## Passo a passo

### 1. Abrir a tela

Menu **Financeiro → Auditoria e Controle de Recursos de Glosas → Lançamentos → Glosa por
Procedimento**.

### 2. Localizar a conta de teste

No campo **Conta/Lote**, digite `100000` (conta real do piloto — ajuste pro número real
da sua base) e confirme a busca. Confira se os campos no topo aparecem assim:

- Paciente: (nome do paciente da conta piloto)
- Convênio: 20 — CAPESAUDE - CAPESESP
- Remessa: 90001
- Vl. Total Conta: 18.994,64

### 3. Achar os 3 itens de teste

Na grid, procure pelos códigos `08020760`, `07020468` e `08012765` (pode ordenar
clicando no cabeçalho "Proced." pra facilitar). Clique em cada um pra ver os detalhes
na parte de baixo da tela — confira se aparece "TESTE PILOTO" no campo Observação.

### 4. Testar os botões (com cuidado, só nos 3 itens de teste)

Selecione **um** dos 3 itens de teste e, **um botão de cada vez**, experimente:

1. **Confirmar Aceite** — o que pede? O que acontece depois?
2. **Ent. Recurso** (Entregar Recurso) — este é o mais importante. Anote:
   - Abre uma tela nova? Pede algum campo que ainda não preenchemos?
   - Gera algum arquivo (XML, PDF, impressão)?
   - Dá algum erro? Se der, **copia a mensagem completa**.
3. **Entr. Rec. Recurso** — mesma coisa: o que pede, o que gera.
4. Se algum botão travar ou pedir algo que vocês não sabem responder, **para e anota o
   que apareceu** — não preenche nada "no chute" pra não confundir o teste.

### 5. Reportar

Depois do teste, me manda:
- Prints de cada tela que abriu ao clicar nos botões.
- Qualquer mensagem de erro, completa (não só o resumo).
- O que pareceu fazer sentido e o que pareceu confuso ou incompleto.

## Se algo der errado

Nada do que será feito aqui afeta o faturamento real — os 3 itens são isolados e
marcados como teste. Se algo parecer ter ido longe demais (gerou um protocolo de
verdade, por exemplo), **para e me chama** antes de continuar clicando.
