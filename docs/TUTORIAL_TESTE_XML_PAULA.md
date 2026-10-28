# Tutorial — teste de XML com a equipe de Recurso de Glosas

## Antes de começar

- Acesse o painel local (endereço interno fornecido pela equipe de TI), ex.: `http://localhost:8877`.
- Cada pessoa deve entrar com sua própria conta.
- Use somente XML TISS do tipo `DEMONSTRATIVO_ANALISE_CONTA`.
- A importação é local: não envia arquivo à CAPESESP e não escreve no MV.

## 1. Importar e conciliar o XML

1. Na tela **Visão geral**, clique em **Importar XML**, no canto superior direito.
2. Selecione o arquivo `.xml` recebido da operadora.
3. Confira o nome do arquivo na confirmação e clique em **OK**.
4. Aguarde a mensagem com as quantidades de itens confirmados, prováveis e não localizados.
5. O painel recarregará a nova análise automaticamente.

Ao importar, o sistema arquiva o contrato e as decisões anteriores. O XML original não é
guardado. A conciliação usa o snapshot local, somente leitura, da guia correspondente no MV.
Se não houver snapshot para a guia, a importação será recusada sem alterar a análise atual.

## 2. Revisar com a equipe

1. Abra **Análise de glosas**.
2. Comece pelos itens **Confirmados**.
3. Para cada item, selecione **Recorrer**, **Aceitar glosa** ou mantenha **Aguardando**.
4. Informe o valor recursado e uma justificativa objetiva.
5. Nos itens **Prováveis**, compare obrigatoriamente descrição, código, data e valor com o MV.
6. Marque **Correspondência confirmada** somente depois da conferência humana.
7. Clique em **Salvar rascunho**.

Itens não localizados não podem ser incluídos no recurso. Justificativas têm limite ponderado
de 150 caracteres e devem ser conferidas antes do uso.

## 3. Gerar o XML de recurso

1. Abra **Montar recurso**.
2. Confira os números de guia com as colunas J/K do demonstrativo.
3. Preencha todos os campos de identificação.
4. Marque a confirmação manual das guias.
5. Confira a checklist lateral.
6. Clique em **Validar e gerar XML**.
7. Quando a validação terminar, clique em **Baixar último XML**.

## 4. Conferência antes do encaminhamento

- Protocolo, lote, guia do prestador e guia da operadora estão corretos.
- Somente itens aprovados pela equipe responsável estão como `RECORRER`.
- Valores não excedem o valor glosado.
- Itens prováveis têm confirmação manual.
- Justificativas e documentos comprobatórios estão completos.
- O XML passou pela validação XSD sem erro.
- O código do evento é exatamente o mesmo da cobrança original; a CAPESESP não aceita
  mudança de código por justificativa.
- O prazo contratual e a janela do grupo de faturamento foram conferidos.

## 5. Enviar à CAPESESP somente depois da aprovação

1. Faça o upload do XML de `RECURSO_GLOSA` no **Portal Protheus**, dentro da janela do grupo
   de faturamento aplicável.
2. Anote o número de protocolo devolvido pelo portal.
3. No site da CAPESESP, acesse **Atendimento Virtual → Menu Credenciado → Interações de Rede
   Credenciada → Nova Solicitação → Rede Credenciada Movimentações → Recurso de glosa — Enc.
   Processos digitalizados**.
4. Anexe a documentação comprobatória ou a carta com a justificativa e envie.
5. Somente depois da confirmação do portal, registre o envio no controle interno.

O manual informa que é permitido apenas um recurso por protocolo/PEG. Portanto, não faça um
upload de teste no Portal Protheus com protocolo real. O teste deve terminar no download e na
validação local do XML; o encaminhamento só ocorre após aprovação final.

Referência conferida: `manual_recurso_glosa_eletronico_06_2023.pdf`, manual oficial da
CAPESESP (mantenha uma cópia local fora deste repositório).
