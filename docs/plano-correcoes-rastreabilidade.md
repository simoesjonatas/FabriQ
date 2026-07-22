# Plano de correções — OP, Dossiê do Lote, Rastreabilidade e Auditoria

> **Documento de referência:** "Complementação Funcional do ERP Industrial" — Laboratórios Corpo & Cheiro, v1.0, julho/2026 (`Orientacoes_ERP_OP_Dossie_Rastreabilidade_Corpo_e_Cheiro.pdf`), complementado pelas **observações do cliente de 18/07/2026** (lote interno automático, etiqueta de MP e responsáveis por atividade — Etapa 2).
>
> **Princípio central do cliente:** o ERP não deve apenas informar que uma produção foi concluída — deve **comprovar como foi executada**: quais lotes foram consumidos, quem realizou cada atividade, quais resultados foram obtidos, quem aprovou e para onde o produto foi enviado.

> ⚠️ **Condição de homologação:** enquanto houver interdição sanitária, todos os testes devem usar **dados fictícios**. O sistema não deve registrar nem justificar fabricação real nesse período.

---

## 1. Mapa: exigência do PDF × estado atual do código

| # PDF | Exigência | Estado atual | Etapa do plano |
|---|---|---|---|
| 2.1 / 5.2 | OP não pode concluir com material sem lote; consumo real por lote (P1) | Consumo é automático em FEFO na conclusão (`ExecucaoOP.concluir`); `MaterialOP` não guarda lote — coluna "Lote usado" fica vazia | Etapa 4 ✅ |
| 2.2 / 4 / 8 | Dossiê do lote consolidado + PDF fechado (P1) | Não existe | Etapa 12 ✅ |
| 2.3 / 7.1 | Trilha de auditoria campo a campo, não apagável (P1) | Só `criado_por`/`atualizado_por` (`ModeloAuditado`) e históricos em texto livre (`HistoricoOP`, `HistoricoPedido`) | Etapa 1 ✅ |
| 2.4 / 4.2 | Snapshot imutável da fórmula na emissão da OP, com versão | `MaterialOP` congela apenas quantidades escaladas; a `Formula` em si é editável e a OP aponta para ela por FK, sem versão | Etapa 3 ✅ |
| 2.5 | Rastreabilidade para trás e para frente (P1) | Dados parciais em `Movimentacao`; não há telas de consulta | Etapa 11 ✅ |
| 2.6 / 7.2 | Bloqueios sistêmicos com exceção justificada (P2) | Alguns bloqueios existem (saldo, quarentena); faltam: lote vencido/reprovado, equipamento inapto, balança vencida, expedição sem CQ etc. | Etapa 5 ✅ |
| 3.1–3.3 | Navegação por links: cliente, pedido, produto | Telas existem, mas sem fichas consolidadas nem links cruzados completos | Etapa 10 ✅ |
| 4.1 | Situação controlada do lote (em produção → aguardando CQ → aprovado → … → expedido/recolhido) | `Lote` não tem campo de situação; quarentena é só por local de estoque | Etapa 5 ✅ |
| 5.1 | Identificação completa da OP (linha, supervisor etc.) | `OrdemProducao` tem equipamento/operador; falta linha, supervisor, prazo | Etapa 6 ✅ |
| 5.3 | Pesagem com dupla conferência e balança calibrada | Não existe | Etapa 6 ✅ |
| 5.4 | Equipamento: limpeza, calibração, checklist pré/pós-uso | `Equipamento` é cadastro simples, sem status/limpeza/calibração | Etapa 6 ✅ |
| 5.5 | Etapas do processo com parâmetros previsto × real | `Formula` não tem etapas; execução não registra etapas | Etapa 6 ✅ |
| 5.6 | Controle em processo com limites da especificação | `TipoAnalise` tem faixas, mas não há controle em processo vinculado à OP | Etapa 6 ✅ |
| 5.7 | Envase/embalagem/rotulagem com lotes e versão de arte | Não existe (embalagens são consumidas como material comum) | Etapa 7 ✅ |
| 5.8 | Perdas e rendimento com limite e aprovação | `ExecucaoOP.perdas` é um número simples, sem limite/justificativa | Etapa 7 ✅ |
| 5.9 | Desvios com decisão da Qualidade; OP não encerra com desvio pendente | `Ocorrencia` é texto livre, sem fluxo de decisão | Etapa 7 ✅ |
| 5.10 | CQ final obrigatório antes de expedir; contra-análise | `Analise` existe sobre `Lote`, mas nada impede expedir sem CQ | Etapa 8 ✅ |
| 5.11 | Assinaturas/aprovações por fase, com perfil | Só `liberado_por` na OP e `decidido_por` na análise | Etapa 8 ✅ |
| 3.2 / 7.2 | Expedição vinculada a lote liberado; expedição parcial | Expedição é só transição de status do pedido (`FINALIZADO → EXPEDIDO`), sem vínculo com lote nem baixa de estoque | Etapa 9 ✅ |
| 6.1 | Ficha da MP (INCI, CAS, FISPQ, fornecedores aprovados) e do lote recebido | `MateriaPrima` é `ItemBase` simples; recebimento já guarda NF/anexos/quarentena | Etapa 10 ✅ |
| 6.2 | Ficha da embalagem + versão de arte | `Embalagem` simples, sem versão de arte | Etapa 10 ✅ |
| 9 | Roteiro de aceite completo (14 passos) | — | Etapa 13 ✅ |

**Observações complementares do cliente (18/07/2026):**

| Observação | Estado atual | Etapa do plano |
|---|---|---|
| Na OP, registrar o que cada funcionário fez (quem produziu, envasou, passou lote) | Só `iniciado_por`/`concluido_por` na execução e `liberado_por` na OP — nada por atividade | Etapa 2 ✅ |
| Lote interno automático, alfanumérico e sequencial (MP no recebimento e produto acabado na OP) | `Lote.codigo` é digitado manualmente; não há campo separado para o lote do fornecedor | Etapa 2 ✅ |
| Etiqueta de identificação da MP (modelo no Anexo A) com status e liberação CQ | Não existe impressão de etiqueta | Etapa 2 ✅ |

**Ordem de execução recomendada:** 1 ✅ → 2 ✅ → 3 ✅ → 4 ✅ → 5 ✅ → 6 ✅ → 7 ✅ → 8 ✅ → 9 ✅ → 10 ✅ → 11 ✅ → 12 ✅ → **13**.
Etapas 1 a 12 concluídas (22/07/2026), além do Anexo A. Falta só a Etapa 13 — homologação com o roteiro de aceite final.
A trilha de auditoria veio primeiro porque todas as demais etapas gravam nela. A Etapa 2 entra na sequência por decisão do cliente (observações de 18/07/2026). O dossiê vem por último porque apenas consolida o que as etapas anteriores passam a registrar.

---

## Etapa 1 — Trilha de auditoria (P1) ✅ CONCLUÍDA (18/07/2026)

**Objetivo (PDF 2.3 e 7.1):** histórico técnico não apagável de todas as ações e alterações: campo, valor anterior, valor novo, usuário, data, hora e justificativa.

> **Status:** implementada e testada (196 testes do projeto passando; critério de aceite
> verificado também na tela real).
> - App `apps/auditoria`: `RegistroAuditoria` imutável (save/delete/queryset bloqueados
>   com `TrilhaImutavelError`), admin somente leitura, badge por ação.
> - Integração automática em `ModeloAuditado.save()` (`apps/core/models.py`): criação e
>   alteração campo a campo de TODOS os modelos auditados alimentam a trilha sem código
>   nas views; `salvar_com_usuario` ganhou o parâmetro `justificativa`.
> - Campos críticos em `apps/auditoria/campos_criticos.py`; `JustificativaAuditoriaMixin`
>   aplicado a `FormulaForm`, `OrdemProducaoForm` e `PedidoForm` (sem justificativa →
>   erro de validação).
> - Eventos com ação própria: liberação de OP, cancelamento de OP/pedido, aprovação de
>   análise (parecer vira justificativa) e decisão de quarentena (gravada na trilha do lote).
> - Partial `templates/includes/trilha_auditoria.html` nas telas: OP, pedido, análise,
>   recebimento, edição de fórmula e edição de cadastros (`CadastroUpdateView`).
> - Limitação registrada: linhas de formsets filhos (`ComponenteFormula`, `ItemPedido`,
>   `ResultadoAnalise`) ainda não geram registro campo a campo próprio — a imutabilidade
>   real desses dados vem com o versionamento da fórmula (Etapa 3) e a contra-análise
>   (Etapa 8). Inativação (`ativo` True→False) é detectada e gravada como ação "Inativação".

### Passos
1. Criar app `apps/auditoria` com o modelo `RegistroAuditoria`:
   - `content_type` + `object_id` (GenericForeignKey) para apontar qualquer registro;
   - `acao` (choices: criação, alteração, cancelamento, inativação, aprovação, liberação, exceção de bloqueio);
   - `campo`, `valor_anterior`, `valor_novo` (texto);
   - `usuario` (FK PROTECT), `data` (`auto_now_add`), `justificativa`;
   - sem tela de edição/exclusão; sobrescrever `save()` para impedir update e `delete()` para levantar exceção — trilha é **imutável**.
2. Criar utilitário `registrar_alteracoes(instancia_antiga, instancia_nova, usuario, justificativa="")` que compara campo a campo e cria um `RegistroAuditoria` por campo alterado. Integrar ao `ModeloAuditado.salvar_com_usuario` (`apps/core/models.py`) ou a um mixin de formulário usado pelas views.
3. Definir a lista de **campos críticos** que exigem `justificativa` obrigatória (PDF: fórmula, lote, quantidade, resultado, status, aprovação, validade). Sem justificativa → `ValidationError` no form.
4. Cancelamento/inativação nunca remove a trilha: `on_delete=PROTECT` em tudo e nenhuma exclusão física por usuário comum (já é a convenção do projeto — manter).
5. Criar partial `templates/includes/trilha_auditoria.html` (aba/accordion) e incluir nas telas críticas: pedido, produto, fórmula, recebimento, lote, OP, análise, desvio, liberação e expedição.
6. Permissões: nenhum perfil comum pode alterar/apagar trilha (não registrar modelos de auditoria em forms/admin editáveis).
7. Testes: alterar campo crítico sem justificativa (bloqueia), com justificativa (grava anterior/novo/usuário/motivo), tentativa de update/delete no registro de auditoria (falha).

### Critério de aceite (PDF)
Alterar um campo de teste e confirmar que o sistema registra automaticamente valor anterior, valor novo, usuário, data, hora e motivo.

---

## Etapa 2 — Complementos do cliente: lote interno automático, etiqueta de MP e responsáveis por atividade na OP ✅ CONCLUÍDA (19/07/2026)

**Origem:** observações enviadas pelo cliente em 18/07/2026 (fora do PDF). Inserida logo após a Etapa 1; as etapas seguintes foram renumeradas.

> **Status:** implementada e testada (211 testes do projeto passando; critérios de aceite
> verificados também nas telas, com a base de demonstração).
> - **2a:** `SequenciaLote` + `gerar_lote_interno`/`criar_lote_interno`
>   (`apps/estoque/models.py`) — formato `MP/EMB/PA-AAAA-NNNNN`, sequência por tipo e
>   ano com `select_for_update`, colisão com códigos antigos avança a sequência.
>   `Lote.lote_fornecedor` novo (campo crítico na trilha); recebimento pede só o lote do
>   fornecedor; `OrdemProducao.lote_produto` é reservado na liberação
>   (`reservar_lote_produto`) e confirmado na conclusão — `ExecucaoOP.concluir()` perdeu
>   o `lote_codigo` digitado (OPs antigas sem reserva geram o lote na conclusão, pela
>   mesma sequência). Lote fornecedor exibido em estoque/recebimento/quarentena.
> - **2b:** etiqueta em `recebimento/itens/<pk>/etiqueta/` (template standalone com os
>   campos do Anexo A); situação espelha `StatusQuarentena`, que ganhou **Em análise** e
>   **Devolvido** (devolução só após reprovação, com observação obrigatória; a saída
>   física do material devolvido é uma movimentação de estoque à parte).
>   `Recebimento.cliente` (terceirização) sai na etiqueta. Cada impressão gera
>   `RegistroAuditoria` com ação **Impressão** na trilha do lote. Botões na tela do
>   recebimento e na fila de quarentena (a ficha do lote vem na Etapa 10).
> - **2c:** `AtividadeOP` imutável (`apps/producao/models.py`) com painel "Quem fez o
>   quê" no detalhe da OP, no painel de produção e na impressão. Automáticas: liberação
>   da OP, atribuição de lote, produção iniciada/concluída; manuais (envase, separação,
>   conferência, outro) via formulário no painel da OP em produção.
> - `carregar_demo` atualizado: lotes internos gerados, códigos antigos viram lote do
>   fornecedor, atividades registradas nas OPs de demonstração.

> **Nota de interpretação** (confirmar com o cliente se necessário): "lote do produto (lote interno) e lote do produto que ele vai ter quando receber a MP" foi entendido como **dois lotes internos automáticos** — o da matéria-prima, atribuído no recebimento (mantendo o lote do fornecedor como campo separado), e o do produto acabado, atribuído/reservado na OP. Os passos abaixo cobrem os dois.

### 2a. Lote interno automático (alfanumérico e sequencial)

**Estado atual:** `Lote.codigo` (`apps/estoque/models.py`) é digitado manualmente tanto no recebimento (`ItemRecebimento` → `Lote`) quanto na conclusão da OP (`ExecucaoOP.concluir(lote_codigo=...)`); não existe campo separado para o lote do fornecedor.

1. Separar os dois conceitos no `Lote`:
   - `codigo` passa a ser o **lote interno**, gerado automaticamente;
   - novo campo `lote_fornecedor` (texto, opcional — obrigatório para lotes criados via recebimento; preenchido com o lote impresso pelo fornecedor).
2. Criar gerador sequencial `gerar_lote_interno(tipo_item)`:
   - formato **alfanumérico e sequencial** configurável, ex.: `MP-2026-00001`, `EMB-2026-00001`, `PA-2026-00001` (prefixo por tipo de item + ano + sequência);
   - sequência controlada por modelo `SequenciaLote` (tipo, ano, último número) com `select_for_update` na transação, para nunca gerar número duplicado;
   - unicidade já garantida pelas constraints existentes (`lote_unico_por_*`).
3. **Recebimento:** ao salvar o `ItemRecebimento`, o lote interno é criado automaticamente; o formulário deixa de pedir o código e passa a pedir apenas lote do fornecedor + validade (+ data de fabricação, se aplicável).
4. **OP / produto acabado:** o lote interno do produto é gerado automaticamente — **reservado já na liberação da OP** (para constar na impressão da OP e nas etiquetas) e confirmado na conclusão, substituindo o campo digitado `lote_codigo` de `ExecucaoOP.concluir()`.
5. Alteração manual de lote interno: somente com permissão específica + justificativa (campo crítico da trilha — Etapa 1).
6. Migração: lotes existentes mantêm o código atual; a sequência vale para novos lotes.
7. Testes: dois recebimentos concorrentes não geram o mesmo número; lote interno criado no recebimento e na liberação/conclusão da OP; `lote_fornecedor` gravado e exibido nas telas de estoque, recebimento e OP.

### 2b. Etiqueta de identificação da matéria-prima

Modelo de referência do cliente no **Anexo A** (layout livre — o conteúdo é o que vale).

1. Nova view de impressão de etiqueta por item de recebimento/lote em `apps/recebimento`, com CSS de impressão (mesmo padrão de `templates/ordens/imprimir.html`), contendo: nome da MP, código interno, fornecedor, nº da NF, lote do fornecedor, lote interno, data de recebimento, validade, cliente (quando material de cliente), situação atual (checkbox marcado), data da liberação CQ, responsável pela liberação e localização.
2. Situação impressa espelha o status do item (`StatusQuarentena`, `apps/recebimento/models.py`): acrescentar os status **"Em análise"** e **"Devolvido"** ao fluxo de decisão da quarentena (hoje: em quarentena, liberado, reprovado, bloqueado) para cobrir os estados da etiqueta.
3. Novo campo `cliente` (FK opcional) no recebimento ou no lote, para material que pertence a um cliente (terceirização) — impresso na etiqueta.
4. Data da liberação CQ e responsável vêm da `DecisaoQuarentena`; localização vem do local de estoque atual do lote.
5. Reimpressão permitida; **cada impressão registrada na trilha** (ação própria) — permite rastrear etiqueta desatualizada.
6. Botões de impressão: na tela do recebimento (por item) e na ficha do lote.
7. O mesmo mecanismo fica preparado para a etiqueta do **lote de produto acabado** (usar após a Etapa 8, com situação de CQ do lote).
8. Futuro (não bloqueia a entrega): código de barras/QR com o lote interno.
9. Testes: etiqueta de lote em quarentena (checkbox correto, campos de liberação em branco) e de lote liberado (data e responsável preenchidos).

### 2c. Responsáveis por atividade na OP (quem produziu, envasou, passou lote)

**Estado atual:** a execução registra `iniciado_por`/`concluido_por` e a OP registra `liberado_por`; não há registro **por atividade**.

1. Novo modelo `AtividadeOP` em `apps/producao`: OP, atividade (choices: produção, envase, atribuição de lote, separação, conferência, outro), funcionário (FK usuário), data/hora, observação — imutável (padrão da Etapa 1).
2. Registro **automático** onde já existe evento: iniciar produção, concluir produção, liberar OP e gerar lote interno (2a) criam a atividade correspondente.
3. Registro **manual** para as demais (envase, passagem de lote, separação) enquanto os módulos específicos não existem — formulário simples na tela da OP em produção.
4. Painel **"Quem fez o quê"** no detalhe da OP (`templates/ordens/detalhe.html`) e na impressão: atividade, funcionário, data/hora, observação.
5. Integração futura: quando as Etapas 6 (pesagem/etapas), 7 (envase) e 8 (assinaturas por fase) entrarem, seus registros alimentam o mesmo painel — `AtividadeOP` é a visão unificada por funcionário.
6. Testes: iniciar/concluir OP gera atividades automáticas; atividade manual de envase aparece no painel com usuário e data/hora.

### Critérios de aceite
- Receber uma MP e conferir: lote interno gerado automaticamente (alfanumérico e sequencial), lote do fornecedor gravado e etiqueta impressa com todos os campos do modelo do Anexo A.
- Concluir uma OP e conferir o lote interno automático do produto acabado (visível desde a liberação).
- Abrir a OP e identificar, com nome e data/hora, quem produziu, quem envasou e quem passou o lote.

---

## Etapa 3 — Versão e snapshot imutável da fórmula (P1) ✅ CONCLUÍDA (19/07/2026)

**Objetivo (PDF 2.4 e 4.2):** a emissão da OP congela uma cópia da fórmula; alterações futuras geram nova versão, nunca substituição retroativa.

> **Status:** implementada e testada (220 testes do projeto passando; critério de aceite
> verificado também nas telas com a base de demonstração).
> - `Formula` versionada: `versao` (começa em 1), `status` Vigente/Histórica,
>   `aprovada_por`/`aprovada_em` (preenchidos automaticamente por quem salva a versão em
>   vigor — o fluxo formal de aprovação com perfil vem na Etapa 8), unicidade
>   (`produto`, `nome`, `versao`).
> - Editar fórmula **com OP emitida** (qualquer status) cria a versão `versao + 1`
>   vigente com os componentes do formulário e congela a anterior como histórica —
>   com **justificativa obrigatória** (inclusive quando só os componentes mudam) e
>   evento próprio na trilha. Sem OP, edita em vigor. Produto não pode ser trocado
>   em fórmula com OP; fórmula histórica não abre para edição e não aparece para OP
>   nova (o form só oferece vigentes).
> - `SnapshotFormulaOP` + `ItemSnapshotFormulaOP` imutáveis, congelados na
>   **liberação** da OP: nome, versão, data da versão, rendimento, instruções e itens
>   com quantidade teórica × escalada (código/nome/unidade copiados como texto —
>   sobrevivem a renomeações de cadastro). `MaterialOP` segue como lista operacional.
> - Telas: detalhe e impressão da OP mostram **número e data da versão congelada**;
>   lista de fórmulas mostra versão + badge Vigente/Histórica (históricas ficam com
>   cadeado, sem edição); o form avisa quando a edição vai gerar nova versão.
> - OPs liberadas ANTES desta etapa não ganham snapshot retroativo (seria evidência
>   falsa) — as telas toleram a ausência; a partir de agora toda liberação congela.
> - `carregar_demo`: OPs de demonstração congelam snapshot; fórmulas demo buscadas
>   pela versão vigente.

### Passos
1. Em `apps/ordens/models.py`, adicionar versionamento à `Formula`:
   - campos `versao` (inteiro, começa em 1), `status` (vigente / histórica), `aprovada_por`, `aprovada_em`;
   - editar uma fórmula **que já tem OP emitida** passa a criar uma nova `Formula` com `versao + 1` e marcar a anterior como histórica (a view de edição decide: sem OP → edita em vigor; com OP → nova versão);
   - unicidade: (`produto`, `nome`, `versao`).
2. Criar `SnapshotFormulaOP` (uma por OP) preenchido na **liberação** da OP:
   - código/nome da fórmula, `versao`, data da versão, rendimento, instruções de fabricação;
   - itens do snapshot: item (MP/embalagem), quantidade teórica para o rendimento base e quantidade escalada — substitui/complementa o atual `gerar_materiais()`;
   - snapshot é imutável (mesma técnica da Etapa 1).
3. Exibir na tela da OP (`templates/ordens/detalhe.html`) e na impressão (`imprimir.html`): **número e data da versão congelada** da fórmula.
4. Bloqueio (registrar na trilha): tentativa de editar fórmula vinculada a OP emitida sem gerar nova versão.
5. Testes: emitir OP → alterar fórmula padrão → OP antiga mantém composição, instruções e versão originais; nova OP usa a versão nova.

### Critério de aceite (PDF)
Alterar a fórmula padrão após a emissão de uma OP de teste e confirmar que a OP antiga mantém os dados originais.

---

## Etapa 4 — Consumo por lote obrigatório na OP (P1) ✅ CONCLUÍDA (20/07/2026)

**Objetivo (PDF 2.1 e 5.2):** a OP registra o consumo **real** por lote — nunca conclui com lote vazio. Hoje a baixa é automática (FEFO) e a coluna "Lote usado" fica vazia na OP concluída.

> **Status:** implementada e testada (225 testes do projeto passando; critério de aceite
> verificado nas telas com a base de demonstração — OP concluída com baixa por lote e a
> coluna "Lote usado" preenchida).
> - `ConsumoMaterialOP` em `apps/producao` (FK `MaterialOP`, `Lote`, `LocalEstoque`,
>   quantidade, FK `Movimentacao` de saída, `registrado_por/em`). Reapontável enquanto
>   `movimentacao` é nula; **imutável** depois de confirmado na conclusão (save/delete/
>   queryset bloqueados como na Etapa 1).
> - Serviços: `posicoes_consumiveis` (fora da quarentena, só com lote, validade em dia,
>   FEFO), `sugerir_consumos_fefo`, `apontar_consumos` (valida lote apto + saldo) e
>   `apontar_consumos_fefo` (automático, usado pela demo).
> - `ExecucaoOP.concluir()` deixou de baixar FEFO automático: gera uma SAÍDA por
>   consumo apontado. Bloqueios: material sem lote (lista quais faltam), lote vencido no
>   apontamento, e divergência soma≠necessário exige justificativa (evento na trilha).
>   Removidos `consumir_material_fefo`/`ProducaoInsuficiente`.
> - Tela de apontamento `producao/<pk>/lotes/`: por material, posições (lote interno,
>   fornecedor, validade+alerta, local, saldo) com quantidade editável pré-carregada
>   pela sugestão FEFO ou pelo apontamento salvo. Painel de produção mostra lote
>   apontado por material, bloqueia a conclusão se faltar lote, e o modal de conclusão
>   tem o campo de justificativa de divergência.
> - Coluna **"Lote usado"** preenchida no detalhe e na impressão da OP (código,
>   quantidade, fornecedor).
> - Comando `criar_consumos_retroativos`: casa `Movimentacao` de saída
>   (documento = número da OP) com os `MaterialOP` e cria consumos retroativos
>   (idempotente) para OPs concluídas antes desta etapa.
> - Estoque: `Lote.vencido` e `Lote.fornecedor` (do recebimento) como propriedades;
>   `carregar_demo` aponta FEFO antes de concluir.
> - Nota: bloqueio por **situação** do lote (reprovado/bloqueado) vem na Etapa 5 — aqui
>   já barramos quarentena e vencido.

### Passos
1. Criar `ConsumoMaterialOP` em `apps/ordens` (ou `apps/producao`):
   - FK para `MaterialOP`, FK para `Lote`, `quantidade`, FK para a `Movimentacao` de saída gerada;
   - permite **mais de um lote por material**, com quantidade de cada um.
2. Nova tela de apontamento na execução (`apps/producao`): para cada material do snapshot, o operador seleciona lote(s) e quantidade(s).
   - Pré-carregar sugestão FEFO usando `posicoes_para_consumo()` (`apps/estoque/models.py`) — o operador confirma ou troca;
   - mostrar validade e situação de cada lote na seleção.
3. Alterar `ExecucaoOP.concluir()` (`apps/producao/models.py`): em vez de `consumir_material_fefo` automático, baixar o estoque a partir dos `ConsumoMaterialOP` confirmados (uma `Movimentacao` de SAÍDA por lote/local, como hoje).
4. Bloqueios na conclusão:
   - material sem lote informado → **impede** concluir, listando quais faltam;
   - lote vencido, reprovado, bloqueado ou em quarentena → impedido já na seleção (ver Etapa 5);
   - soma das quantidades por lote ≠ necessário → alerta/justificativa.
5. Exibir na OP concluída a coluna "Lote usado" preenchida, com material, lote e fornecedor **clicáveis** (links para as fichas — Etapa 10).
6. Migração de dados: OPs antigas concluídas têm as saídas em `Movimentacao` com `documento = numero da OP` — criar `ConsumoMaterialOP` retroativos a partir delas (comando de gestão).
7. Testes: concluir OP usando **dois lotes do mesmo material** e conferir consumo individual + baixa correta; tentar concluir com material sem lote (bloqueia).

### Critério de aceite (PDF)
Concluir uma OP de teste usando dois lotes de um mesmo material e confirmar o consumo individual e a baixa correta do estoque.

---

## Etapa 5 — Situação do lote e bloqueios sistêmicos (P1/P2) ✅ CONCLUÍDA (20/07/2026)

**Objetivo (PDF 2.6, 4.1 e 7.2):** o sistema **impede** a ação irregular (não só avisa); o lote tem situação controlada.

> **Status:** implementada e testada (232 testes do projeto passando; critério de aceite
> verificado nas telas — lote vencido/reprovado bloqueado com a causa, e exceção
> autorizada gravada na trilha).
> - `SituacaoLote` (EM_PRODUCAO, AGUARDANDO_CQ, EM_ANALISE, APROVADO, REPROVADO,
>   BLOQUEADO, EXPEDIDO, RECOLHIDO, DEVOLVIDO) + campo `Lote.situacao` (default
>   AGUARDANDO_CQ) + `badge_situacao`. Migração com backfill (lotes com decisão de
>   quarentena recebem a situação correspondente).
> - Sincronização: recebido nasce AGUARDANDO_CQ; a `DecidirItemView` mapeia a decisão
>   da quarentena para a situação (liberado→APROVADO, reprovado→REPROVADO,
>   bloqueado→BLOQUEADO, em análise→EM_ANALISE, devolvido→DEVOLVIDO), gravando na
>   trilha do lote; o lote de produto nasce EM_PRODUCAO na reserva e vai a
>   AGUARDANDO_CQ na conclusão (o fluxo de CQ→APROVADO do acabado é a Etapa 8).
> - Serviço no `Lote`: `motivo_bloqueio_consumo()` (mensagem com causa+correção),
>   `pode_ser_consumido()` e `pode_ser_expedido()`. Bloqueiam consumo: vencido +
>   situações REPROVADO/BLOQUEADO/EXPEDIDO/RECOLHIDO/DEVOLVIDO (quarentena já é barrada
>   por local). Aplicado em `posicoes_consumiveis`/`apontar_consumos`.
> - **Exceção de bloqueio**: `pode_autorizar_excecao` (Administrador/Diretoria/
>   Qualidade) em perfis.py; `apontar_consumos(..., excecoes={lote_pk: justificativa})`
>   libera o lote bloqueado e grava `RegistroAuditoria` ação "exceção de bloqueio"
>   (causa + justificativa + usuário). Na tela de apontamento, lotes bloqueados
>   aparecem em vermelho com o motivo; para usuário autorizado, surge o campo de
>   quantidade + justificativa da exceção.
> - Badge de situação nas telas: consulta de saldo, apontamento de lotes. A
>   re-checagem de elegibilidade saiu do `concluir()` — o apontamento é o único ponto
>   de controle (permite honrar exceções); `concluir()` só efetiva a baixa.
> - Nota: os demais bloqueios da lista do PDF 7.2 (liberação sem CQ, expedição de lote
>   não liberado) dependem das Etapas 8–9 e serão fechados lá.

### Passos
1. Adicionar ao `Lote` (`apps/estoque/models.py`) o campo `situacao` com fluxo controlado:
   `EM_PRODUCAO → AGUARDANDO_CQ → APROVADO / REPROVADO`, e ainda `BLOQUEADO`, `EXPEDIDO`, `RECOLHIDO`.
   - Lotes de MP/embalagem: situação alimentada pela decisão de quarentena do recebimento (`DecisaoQuarentena`) — hoje isso é só troca de local; passar a refletir também na situação do lote (incluindo "Em análise" e "Devolvido", acrescentados na Etapa 2b);
   - lote de produto acabado nasce `AGUARDANDO_CQ` ao concluir a OP (ver Etapa 8);
   - transições com registro na trilha; alteração de validade após aprovação exige justificativa (Etapa 1).
2. Centralizar as regras num serviço `lote_pode_ser_consumido(lote)` / `lote_pode_ser_expedido(lote)` e aplicar em todos os pontos de seleção de lote (execução, envase, expedição).
3. Bloqueios obrigatórios (lista do PDF 7.2):
   - material sem fornecedor/lote/validade no recebimento;
   - seleção de lote vencido, em quarentena, reprovado ou bloqueado;
   - fórmula alterada após emissão (Etapa 3);
   - OP concluída sem lotes, sem perdas registradas ou sem quantidade final;
   - liberação de lote sem CQ; expedição de lote não liberado (Etapas 8–9).
4. Mensagem de bloqueio deve **indicar a causa e o registro a corrigir** (ex.: "Lote MP-0042 vencido em 02/07/2026 — registre nova análise ou selecione outro lote").
5. Exceções: permissão específica (novo perfil/permissão em `apps/accounts/perfis.py`) + justificativa obrigatória + `RegistroAuditoria` com ação "exceção de bloqueio".
6. Testes: tentar selecionar lote vencido e em quarentena (impede e informa causa); exceção autorizada grava usuário, motivo e aprovação.

### Critério de aceite (PDF)
Tentar selecionar um lote vencido ou em quarentena e confirmar que o sistema impede a continuidade e informa a causa.

---

## Etapa 6 — Execução detalhada: identificação, pesagem, equipamentos, etapas e controle em processo (P1) ✅ CONCLUÍDA (20/07/2026)

**Objetivo (PDF 5.1, 5.3–5.6):** a OP comprova **como** o processo foi executado, não apenas início e fim.

> **Status:** implementada e testada (247 testes do projeto passando; critérios de aceite
> de 6a–6e verificados, com telas conferidas na base de demonstração).
> - **6a:** `OrdemProducao` ganhou `linha` (FK Setor), `supervisor` (FK user) e `prazo`;
>   form/detalhe/impressão exibem. Regra: cliente e produto **ativos** para emitir OP.
> - **6b:** cadastro `Balanca` (com `calibracao_vencida`); `MateriaPrima.critico`;
>   `PesagemOP` + serviço `registrar_pesagem` com bloqueios: balança vencida, dupla
>   conferência de material crítico (conferente ≠ operador) e resultado fora da
>   tolerância. Tela `producao/<pk>/pesagem/`.
> - **6c:** `Equipamento` estendido (status liberado/manutenção/interditado,
>   ultima_limpeza/sanitizacao, manutencao_validade, calibracao_validade, localizacao)
>   com `motivo_impedimento_uso()`/`pode_ser_usado()`; a liberação da OP bloqueia
>   equipamento em manutenção/interditado/sem limpeza/calibração vencida (nova condição
>   em `condicoes_liberacao`). `ChecklistEquipamentoOP` registrado no modelo (para o
>   dossiê); UI de preenchimento fica para depois.
> - **6d:** `EtapaFormula` (na fórmula, com formset editável) congelada em
>   `EtapaSnapshotOP` na liberação; `EtapaOP` (execução) via tela `producao/<pk>/etapas/`
>   com `registrar_etapa` que exige sequência e **justificativa para pular** (evento na
>   trilha).
> - **6e:** `EspecificacaoProduto` (qualidade: limite por produto+parâmetro) e
>   `ControleProcessoOP` + `registrar_controle` — usa o limite da especificação do
>   produto (não do tipo genérico), marca `fora_especificacao` e **acumula** (nova
>   medição não apaga a anterior). Tela `producao/<pk>/controles/`.
> - Cadastro de Balanças no módulo Cadastros; badge de situação do equipamento na lista.
> - `carregar_demo._execucao_detalhada`: balanças (uma com calibração vencida), MP
>   crítica, equipamentos aptos, especificação de pH por produto e etapas na fórmula do
>   sabonete.
> - Pendências assumidas (documentadas): UI do `ChecklistEquipamentoOP`; painel de
>   pesagens/etapas/controles no detalhe da OP e no dossiê (virá na Etapa 12); o
>   bloqueio "fora da especificação bloqueia a etapa" hoje é sinalizado (badge/aviso) e
>   acumula — o travamento rígido da etapa se conecta aos desvios da Etapa 7c.

### 6a. Identificação completa da OP (PDF 5.1)
1. Adicionar à `OrdemProducao`: `linha` (FK opcional para novo cadastro ou usar `Setor`), `supervisor` (FK usuário), `prazo` (data limite).
2. Garantir na tela e na impressão: número, pedido, cliente, produto, lote acabado, fórmula+versão, quantidade, data programada, prazo, linha, equipamento, operador, supervisor, status e observações.
3. Regra: cliente e produto devem estar **ativos e liberados** para criar OP (validar no form; ver bloqueio de cliente/produto na Etapa 10).

### 6b. Pesagem e dupla conferência (PDF 5.3)
1. Novo cadastro `Balanca` em `apps/cadastros`: código, descrição, capacidade, `calibracao_validade`.
2. Novo modelo `PesagemOP`: material da OP, lote, quantidade prevista, quantidade pesada, tolerância (%), diferença calculada, balança, operador, conferente, data/hora, identificação da etiqueta.
3. Flag `critico` em `MateriaPrima`: material crítico **exige dupla conferência** (conferente ≠ operador).
4. Bloqueios: balança com calibração vencida não pode ser usada; resultado fora da tolerância impede avanço ou abre desvio (Etapa 7c).
5. Teste de aceite: registrar uma pesagem dentro da tolerância (libera) e outra fora (bloqueia/gera desvio).

### 6c. Equipamentos: limpeza e condição de uso (PDF 5.4)
1. Estender `Equipamento` (`apps/cadastros/models.py`): `status` (liberado, em manutenção, interditado), `ultima_limpeza`, `ultima_sanitizacao`, `manutencao_validade`, `calibracao_validade`, `localizacao`.
2. Novo modelo `ChecklistEquipamentoOP`: OP, equipamento, tipo (pré-uso/pós-uso), itens verificados, responsável pela liberação, condição final, danos, data/hora.
3. Bloqueio: equipamento em manutenção, interditado, sem limpeza registrada ou com calibração vencida **não pode ser usado na OP**.
4. Teste de aceite: selecionar equipamento bloqueado e confirmar que o sistema impede o uso.

### 6d. Etapas do processo produtivo (PDF 5.5)
1. Novo modelo `EtapaFormula` (filho de `Formula`): sequência, instrução, material adicionado (opcional), parâmetros previstos (temperatura, tempo, velocidade). Entra no snapshot da Etapa 3.
2. Novo modelo `EtapaOP` (execução): etapa do snapshot, valores reais (temperatura, tempo, velocidade), início, término, operador, conferente, observações.
3. Regras: etapas seguem a sequência da versão da fórmula; **pular etapa exige justificativa e autorização**; parâmetro fora do limite gera alerta e avaliação da Qualidade.
4. Teste de aceite: executar OP de teste e verificar que cada etapa exige os parâmetros e responsáveis definidos na fórmula.

### 6e. Controle em processo (PDF 5.6)
1. Novo modelo `EspecificacaoProduto` em `apps/qualidade`: produto + `TipoAnalise` + limites (mín/máx) — os limites vêm da **especificação do produto**, não do tipo genérico.
2. Novo modelo `ControleProcessoOP`: OP/etapa, parâmetro (aspecto, cor, odor, pH, viscosidade, densidade, temperatura, peso, volume…), limite aplicado, resultado, método, equipamento, analista, data/hora.
3. Regras: resultado fora da especificação **bloqueia a etapa**; nova medição **não apaga** a anterior (registros acumulam).
4. Teste de aceite: inserir resultado fora do limite → bloqueio, primeiro resultado preservado e abertura de avaliação.

---

## Etapa 7 — Envase, perdas e desvios (P1) ✅ CONCLUÍDA (20/07/2026)

> **Status:** implementada e testada (255 testes do projeto passando; critério de aceite
> do 7c verificado na tela — conclusão bloqueada por desvio pendente).
> - **7a:** cadastro `VersaoArte` (filho de Produto; status aprovada/obsoleta) e
>   `EnvaseOP` + `registrar_envase` — o envase só usa **versão de arte aprovada** do
>   produto (obsoleta é barrada). Tela `producao/<pk>/envase/`; cadastro de Versões de
>   arte no módulo Cadastros. Os lotes de frasco/tampa/rótulo/caixa continuam entrando
>   pelo apontamento de consumo (Etapa 4).
> - **7b:** `Produto.limite_perda_percentual` (default 5%). `ExecucaoOP.concluir()`
>   calcula quantidade teórica, perda % e rendimento % e **bloqueia o encerramento** se a
>   perda ultrapassa o limite sem justificativa/aprovação (registro em
>   `perda_justificativa`/`perda_aprovada_por` + evento na trilha). O modal de conclusão
>   ganhou o campo de justificativa da perda; o painel mostra perda %/rendimento %.
> - **7c:** `Desvio` (tipo, etapa, descrição, impacto, ação imediata, crítico,
>   responsável, status aberto/em avaliação/encerrado, decisão da Qualidade
>   avaliador/decisão/data/justificativa, CAPA). A OP **não encerra com desvio pendente**;
>   `decidir_desvio` (só Qualidade) encerra e, se crítico + reprovado, bloqueia o lote
>   (SituacaoLote.BLOQUEADO — Etapa 5). Tela `producao/<pk>/desvios/` (registro +
>   decisão); ocorrências antigas migradas para desvios encerrados. As `Ocorrencia`
>   informais seguem existindo em paralelo.
> - `carregar_demo`: limite de perda 5%, versão de arte v1 aprovada por produto.
> - Pendência: os campos do EnvaseOP (peso/volume médio, controles) e os painéis de
>   envase/perdas/desvios no dossiê virão na Etapa 12.

### 7a. Envase, embalagem e rotulagem (PDF 5.7)
1. Novo cadastro `VersaoArte` (filho de `Produto`): versão, data de aprovação, arquivo/arte, status (aprovada/obsoleta).
2. Novo modelo `EnvaseOP`: OP, lote do granel, linha, horários de início/fim, quantidade envasada, peso/volume médio, controles, versão de arte utilizada, perdas, operador, conferente.
3. Lotes de frasco, tampa, rótulo e caixa entram como `ConsumoMaterialOP` de embalagens (Etapa 4) — itens **separados** por componente.
4. Regras: rótulo deve estar vinculado à versão de arte **aprovada** do produto; embalagem reprovada/não liberada é bloqueada (Etapa 5); contabilizar material utilizado, devolvido (mantém o mesmo lote ao voltar ao estoque) e perdido.
5. Teste de aceite: abrir o dossiê e localizar os lotes de frasco, tampa, rótulo e caixa utilizados.

### 7b. Perdas e rendimento (PDF 5.8)
1. Adicionar em `Produto` (ou por processo): `limite_perda_percentual` configurável.
2. Na conclusão da OP, calcular automaticamente: quantidade teórica, real, diferença, perda absoluta, perda %, rendimento %.
3. Regras: perda acima do limite exige **justificativa e aprovação** (registro próprio, não observação); sem decisão → encerramento impedido.
4. Teste de aceite: registrar perda acima do limite → sistema exige justificativa e impede encerramento sem decisão.

### 7c. Desvios e ocorrências (PDF 5.9)
1. Evoluir `Ocorrencia` (`apps/producao/models.py`) para `Desvio` (novo modelo; manter dados antigos migrados): tipo, etapa, descrição, impacto, ação imediata, responsável, **decisão da Qualidade** (avaliador, decisão, data, justificativa), anexos/fotos, status (aberto, em avaliação, encerrado), vínculo com não conformidade/CAPA (campo texto/FK futura).
2. Regras: **OP não pode ser encerrada com desvio pendente**; toda decisão tem responsável, data e justificativa; desvio crítico permite bloquear o lote (situação `BLOQUEADO`, Etapa 5).
3. Teste de aceite: abrir desvio em OP → encerramento bloqueado até a decisão da Qualidade.

---

## Etapa 8 — CQ final, liberação e assinaturas por fase (P1) ✅ CONCLUÍDA (20/07/2026)

**Objetivo (PDF 5.10 e 5.11):** produção concluída ≠ produto liberado; cada fase tem responsável identificado.

> **Status:** implementada e testada (261 testes do projeto passando; ambos os critérios
> de aceite verificados — assinaturas por fase na tela da OP; bloqueio/mudança de situação
> do lote por decisão de CQ coberto por testes).
> - Lote acabado já nasce `AGUARDANDO_CQ` na conclusão (Etapa 5); a situação (não o
>   local físico) é o que impede a expedição. O local de quarentena de PA fica para a
>   Etapa 9/expedição.
> - `Analise` estendida: amostra, data_coleta, analista, laudo (PDF) e
>   `analise_anterior` (contra-análise). A **decisão do CQ sobre lote de produto** muda a
>   situação: APROVADA→`APROVADO` (expedível), REPROVADA→`REPROVADO` (na trilha). Lotes de
>   MP seguem a decisão da quarentena.
> - **Contra-análise:** `ContraAnaliseView` cria nova análise vinculada à anterior — os
>   resultados da original ficam **preservados**; botão na tela de detalhe.
> - `LiberacaoFase` (imutável): assinatura por fase (emissão, produção, encerramento,
>   análise, aprovação, liberação técnica...). Registro automático em emitir OP, iniciar
>   e concluir produção, e na decisão do CQ (análise + aprovação). **Liberação técnica**
>   manual (`OrdemLiberacaoTecnicaView`, só perfil que autoriza exceção — Admin/Diretoria/
>   Qualidade), após concluída. Painel "Assinaturas por fase" no detalhe e na impressão da
>   OP.
> - Limites da especificação do produto (Etapa 6e): o controle em processo já os usa;
>   o casamento automático dos ensaios da análise final com a especificação fica como
>   evolução (hoje o analista registra os resultados e decide).
> - `carregar_demo`: OP-00004 com todas as fases assinadas e liberação técnica; lote
>   PA aprovado no CQ vira APROVADO.
> - Pendências: perfis por fase mais granulares e o alerta de "mesma pessoa em etapas
>   incompatíveis" (executou e conferiu) ficam para um refinamento posterior.

### Passos
1. Ao concluir a OP, o lote acabado nasce com situação `AGUARDANDO_CQ` (e entra em local de quarentena de produto acabado, reusando a mecânica de `local_quarentena()`).
2. Estender a análise final (`apps/qualidade`): amostra, data/hora da coleta, analista, ensaios com **limites da especificação do produto** (Etapa 6e), resultados, aprovação/reprovação, laudo/certificado (PDF), observações.
3. Contra-análise: nova análise vinculada à anterior — resultados anteriores **preservados**, nunca sobrescritos.
4. Decisão do CQ muda a situação do lote: aprovado → `APROVADO` (liberado para expedição, sai da quarentena); reprovado → `REPROVADO` (bloqueado).
5. Assinaturas por fase — novo modelo `LiberacaoFase` (ou registros dedicados): emissão, separação, pesagem, conferência, produção, encerramento, análise, aprovação e **liberação técnica**, cada um com usuário autenticado, data/hora. Alimentam também o painel "Quem fez o quê" (Etapa 2c).
6. Perfis (`apps/accounts/perfis.py`): limitar quem pode aprovar/liberar cada fase; mesma pessoa em etapas incompatíveis (ex.: executou e conferiu) → alerta ou justificativa conforme regra interna.
7. Testes: tentar expedir lote `AGUARDANDO_CQ` (bloqueia — depende da Etapa 9); liberar e verificar mudança de situação; consultar OP e identificar quem executou, conferiu e aprovou cada fase com data e hora.

### Critérios de aceite (PDF)
- Tentar expedir um lote aguardando CQ e confirmar o bloqueio; depois liberar e verificar a mudança de status.
- Consultar a OP e identificar claramente quem executou, conferiu e aprovou cada fase, com data e hora.

---

## Etapa 9 — Expedição vinculada a lotes (P1 para o fluxo, P2 na origem) ✅ CONCLUÍDA (22/07/2026)

**Objetivo (PDF 3.2 e 7.2):** pedido só é expedido com vínculo a lote liberado; hoje `FINALIZADO → EXPEDIDO` é uma simples transição de status sem lote nem baixa de estoque.

> **Status:** implementada e testada (268 testes do projeto passando; critério de aceite
> verificado na demo — abrir pedido expedido e ver quais OPs e lotes atenderam cada item).
> - Novo app `apps/expedicao` (`Expedicao`, `ItemExpedicao`) + serviço `registrar_expedicao`:
>   cada linha valida que o lote está `APROVADO` (`pode_ser_expedido`), é do produto do item
>   e tem saldo; gera `Movimentacao` de SAÍDA do produto acabado e passa o lote a `EXPEDIDO`.
> - `Pedido.transicionar` bloqueia `EXPEDIDO` sem ao menos uma `Expedicao` registrada
>   (não é mais uma transição de status "seca").
> - Resumo por item (`apps/expedicao/resumo.py`): pedida / produzida / aprovada / expedida /
>   saldo, com OPs e lotes que atenderam — usado no detalhe do pedido e na tela de expedição.
>   Expedição **parcial** mantém saldo pendente (verificado: 200 de 297 → saldo 100).
> - Telas: lista/detalhe de expedição, formulário por lote aprovado, botão "Expedir" e blocos
>   "Produtos e atendimento" + "Expedições" (NF, transportadora, lote) no detalhe do pedido.
> - Demo: pedido `PED-00007` fica expedido via `registrar_expedicao` (NF + transportadora);
>   `PED-00009` fica finalizado com lote aprovado, pronto para expedir.

### Passos
1. Novo app `apps/expedicao` com `Expedicao` e `ItemExpedicao`:
   - `Expedicao`: pedido, data, NF, transportadora, conferente, responsável, observações;
   - `ItemExpedicao`: item do pedido, **lote acabado** (situação `APROVADO` obrigatória), quantidade;
   - cada item gera `Movimentacao` de SAÍDA do estoque de produto acabado (lote e local).
2. Regras:
   - pedido **não pode** ir para `EXPEDIDO` sem ao menos uma expedição com lote liberado (validar em `Pedido.transicionar`, `apps/pedidos/models.py`);
   - expedição **parcial** mantém saldo pendente por item (pedida × expedida);
   - lote expedido muda situação para `EXPEDIDO`; cancelamentos preservam histórico.
3. Tela do pedido passa a mostrar: quantidades pedida, produzida, aprovada e expedida por item, OPs, lotes, NF e transportadora (fecha o PDF 3.2).
4. Testes: expedir sem lote liberado (bloqueia); expedição parcial mantém pendência; abrir pedido expedido e ver quais OPs e lotes atenderam cada item.

### Critério de aceite (PDF)
Abrir um pedido expedido e visualizar quais OPs e lotes atenderam cada item.

---

## Etapa 10 — Fichas consolidadas e navegação por links (P2) ✅ CONCLUÍDA (22/07/2026)

**Objetivo (PDF 3 e 6):** fluxo navegável nos dois sentidos:
`Cliente → Pedido → Produto → Lote produzido → Dossiê → OP → Fórmula → Materiais → Lotes usados → Fornecedores`.

> **Status:** implementada e testada (300 testes do projeto passando; os dois critérios
> de aceite verificados na demo — abrir o cliente pelo pedido e chegar à MP pela OP com
> lote, fornecedor, validade, análise, consumo e saldo).
> - **Ficha do cliente**: `DocumentoCliente` (AFE/alvará/licença/contrato com validade e
>   alerta de vencimento em 30 dias), `Cliente.responsavel_tecnico`, `Cliente.bloqueado` +
>   `motivo_bloqueio`. Cliente bloqueado sai do seletor de novo pedido e é recusado no
>   `PedidoForm.clean_cliente`; também impede emitir OP.
> - **Ficha do produto**: `categoria`, `apresentacao`, `grau`, `registro_anvisa`,
>   `situacao_regulatoria` (Regularizado/Isento/Em análise/Vencido), `bloqueado`.
>   `Produto.motivo_impedimento_op()` bloqueia OP para produto inativo, bloqueado ou sem
>   regularização (`OrdemProducaoForm.clean`). A ficha reúne fórmula vigente + versões,
>   OPs, lotes, especificações, artes e clientes.
> - **Ficha da MP**: INCI, CAS, especificação, condições de armazenamento, ficha técnica e
>   FISPQ; `fornecedores_aprovados` (M2M). Sem lista definida não restringe; com lista, só
>   lote daqueles fornecedores é consumido.
> - **Ficha da embalagem**: capacidade, material, cor, fabricante, critérios de inspeção,
>   `fornecedores_aprovados` e `versao_arte`. Rótulo com arte **obsoleta** bloqueia o
>   consumo (`Embalagem.motivo_arte_invalida()`).
> - Os bloqueios de fornecedor/arte entram no apontamento (`_impedimento_do_item` em
>   `apontar_consumos`) e são liberáveis por **exceção justificada**, como na Etapa 5.
> - **Ficha do lote** (`estoque:lote_detalhe`): origem (fornecedor, recebimento, NF, data),
>   validade, situação, saldo por local, consumo em OPs, movimentações, análises e — para
>   lote de produto — OP de origem e expedições/cliente de destino.
> - **Navegação**: `get_absolute_url()` em Cliente, Produto, MateriaPrima, Embalagem e Lote
>   alimenta os links cruzados nas telas de pedidos, ordens, estoque, qualidade, expedição
>   e nas listas de cadastro. Novo `AcessoQualquerModuloMixin` libera a ficha para quem
>   acessa qualquer módulo relacionado (a edição continua exigindo Cadastros).
> - Pendências: seções de reclamações/devoluções (módulo inexistente) e o botão
>   "Visualizar dossiê" na tabela de lotes, que depende da Etapa 12.

### Passos
1. **Ficha do cliente** (PDF 3.1): dados cadastrais, contatos, responsável técnico, documentos sanitários (novo modelo `DocumentoCliente` com validade e **alerta de vencimento**), contratos, produtos, pedidos, lotes, reclamações/devoluções/pendências (seções placeholder onde o módulo ainda não existe). Campo `bloqueado`: cliente bloqueado impede novos pedidos ou exige autorização. Nome do cliente clicável em todas as telas (pedido, OP, dossiê).
2. **Ficha do produto** (PDF 3.3): código, cliente, categoria, apresentação, Grau 1/2, processo/registro, situação regulatória, fórmula vigente + **todas as versões** (Etapa 3), versões de arte (Etapa 7a), especificações (Etapa 6e), OPs, certificados e reclamações; tabela de lotes com botão **"Visualizar dossiê"**. Produto bloqueado/sem regularização não gera OP.
3. **Ficha da matéria-prima** (PDF 6.1): estender `MateriaPrima` com INCI, CAS, especificação, condições de armazenamento, ficha técnica e FISPQ (anexos); `fornecedores_aprovados` (M2M com `Fornecedor`) — consumo só de fornecedor qualificado/autorizado. Por lote: fornecedor, fabricante, lote do fornecedor (Etapa 2a), lote interno único, NF, datas (recebimento/fabricação/validade), quantidades, saldo (nunca negativo — já garantido em `Movimentacao.clean`), localização, situação, COA, análise e liberação (linkar com `apps/recebimento`).
4. **Ficha da embalagem** (PDF 6.2): tipo, capacidade, material, cor, fornecedor, fabricante, inspeção; frasco, tampa, rótulo e caixa como itens separados; versão de arte vinculada ao produto e à data de aprovação; lote de rótulo incorreto bloqueia a OP.
5. Transformar em **link** toda referência cruzada nas telas existentes (`templates/ordens/detalhe.html`, `pedidos`, `estoque`, `qualidade`, dossiê): material → ficha; lote → ficha do lote (com fornecedor, validade, recebimento, análise, consumo e saldo); OP ↔ pedido ↔ cliente.
6. Testes de aceite: clicar no cliente do pedido e abrir a ficha sem nova pesquisa; abrir a MP a partir da OP e localizar lote, fornecedor, validade, análise, consumo e saldo.

---

## Etapa 11 — Consultas de rastreabilidade (P1) ✅ CONCLUÍDA (22/07/2026)

**Objetivo (PDF 2.5):** reconstruir a cadeia nos dois sentidos.

> **Status:** implementada e testada (307 testes do projeto passando; critério de aceite
> verificado na demo — do lote de MP até OPs, lotes acabados, quantidades e clientes, e
> depois o caminho inverso).
> - Serviço em `apps/estoque/rastreabilidade.py`, montado só pelos vínculos já gravados
>   (`ConsumoMaterialOP`, `OrdemProducao.lote_produto`, `ItemExpedicao`, `ItemRecebimento`):
>   - `rastrear_para_tras(lote acabado)` → OP(s), fórmula congelada (versão do snapshot),
>     consumos, lote de cada material, recebimento/fornecedor/NF, **quantidade consumida e
>     saldo** por linha; inclui também "quem recebeu" (expedições do lote), que fecha o caso
>     de recolhimento na mesma tela;
>   - `rastrear_para_frente(lote de MP/embalagem)` → consumos, OPs, lote acabado gerado
>     (com saldo), expedições, pedidos e `clientes_atendidos`;
>   - `rastrear(lote)` escolhe o sentido pelo tipo do lote; `buscar_lotes(termo)` procura por
>     **lote interno ou lote do fornecedor**.
> - Tela `estoque:rastreabilidade` com busca, alternância "De onde veio / Para onde foi" e
>   links para OP, pedido, cliente, material, lote, recebimento e expedição. Entradas: aba
>   Rastreabilidade no módulo Estoque e botão "Rastrear" na ficha do lote.
> - Casos de uso do PDF cobertos: investigação (de onde veio), bloqueio (quais lotes acabados
>   usam a MP X) e recolhimento (quais clientes receberam).

### Passos
1. **Para trás:** a partir de um lote de produto acabado → OP(s) → snapshot da fórmula → consumos (`ConsumoMaterialOP`) → lotes de MP/embalagem → recebimentos → fornecedores. Tela: `estoque` ou `ordens` → "Rastreabilidade do lote".
2. **Para frente:** a partir de um lote de MP/embalagem → consumos → OPs → lotes acabados → expedições → pedidos → clientes afetados. Tela com busca por lote interno ou lote do fornecedor.
3. Exibir **quantidades consumidas e saldos** em cada nó (regra do PDF).
4. Casos de uso a validar: investigação (de onde veio?), bloqueio (quais lotes acabados usam a MP X?) e recolhimento (quais clientes receberam?).
5. Testes: selecionar lote de MP e localizar todas as OPs, lotes acabados, quantidades e clientes; caminho inverso a partir do lote acabado.

### Critério de aceite (PDF)
Selecionar um lote de matéria-prima e localizar todas as OPs, lotes acabados, quantidades e clientes relacionados; depois realizar o caminho inverso.

---

## Etapa 12 — Dossiê do lote + geração de PDF (P1) ✅ CONCLUÍDA (22/07/2026)

**Objetivo (PDF 2.2, 4 e 8):** visão única e completa do lote, gerada automaticamente a partir dos vínculos do banco, com exportação em PDF fechado.

> **Status:** implementada e testada (317 testes do projeto passando; os dois critérios de
> aceite verificados na demo — do pedido expedido até o dossiê completo, e PDF com todos os
> blocos identificando quando e por quem foi gerado).
> - Novo app `apps/dossie`. `servicos.montar_dossie(lote)` monta os 13 blocos **só pelos
>   vínculos do banco** (consumos, snapshot, pesagens, etapas, controles, envase, desvios,
>   liberações, análises, expedições e trilha) — nada é digitado. Recusa lote que não seja
>   de produto acabado.
> - Tela `dossie:detalhe` com os blocos e links para produto, cliente, pedido, OP, material,
>   lote, recebimento, análise e expedição. Acesso pelo pedido expedido, pela ficha do
>   produto (botão "Visualizar dossiê" na tabela de lotes), pela ficha do lote e pela OP.
> - **PDF com WeasyPrint** (`weasyprint>=62` em requirements/base.txt; precisa de
>   pango/cairo/gdk-pixbuf no sistema): capa + todos os blocos, rodapé em toda página com
>   "Gerado pelo FabriQ em … por … · código · versão" e paginação.
> - **Cada geração é um registro**: `GeracaoDossie` imutável (lote, versão sequencial,
>   usuário, data/hora, SHA-256 e o próprio PDF). A tela lista o histórico de gerações.
> - O banco segue sendo a fonte oficial; o PDF é a evidência consolidada do instante.
> - `carregar_demo` ganhou `_execucao_no_chao()`: a OP do pedido expedido passou a ter
>   pesagem com dupla conferência, checklist, etapas, controle em processo, envase e um
>   desvio já avaliado — assim o dossiê da demo sai com os 13 blocos preenchidos.
> - Pendência: anexos grandes ainda são listados por vínculo, não embutidos no PDF.

### Passos
1. Nova view "Dossiê do lote" (por lote de produto acabado), montada **automaticamente pelos vínculos do banco** — sem digitação manual. Blocos, na ordem do PDF:
   1. **Identificação e situação** (4.1): produto, cliente, pedido, OP, lote acabado, fabricação, validade, quantidades prevista/produzida/aprovada/reprovada, perdas, rendimento e situação;
   2. **Fórmula e versão utilizadas** (4.2): snapshot imutável, diferenças teórico × pesado, link para a ficha da fórmula original;
   3. **Materiais, lotes e documentos** (4.3): separados por MP, embalagem primária/secundária, rótulos e auxiliares — cada linha com links para ficha do material, lote, fornecedor, recebimento, COA, análise interna e NF;
   4. Pesagens e conferências (5.3);
   5. Equipamentos e checklists (5.4);
   6. Etapas do processo com parâmetros (5.5);
   7. Controles em processo (5.6);
   8. Envase/embalagem/rotulagem com lotes e versão de arte (5.7);
   9. Perdas e rendimento (5.8);
   10. Desvios e decisões (5.9);
   11. CQ final, laudo e liberações/assinaturas (5.10–5.11);
   12. Expedições (Etapa 9);
   13. Trilha de auditoria (Etapa 1).
2. Acesso: botão "Visualizar dossiê" na tabela de lotes do produto (Etapa 10), no detalhe da OP e no pedido expedido.
3. **Geração de PDF** (WeasyPrint ou similar, novo requirement):
   - capa + todos os blocos acima;
   - rodapé com **data/hora de geração, usuário gerador, versão, paginação, código do dossiê e identificação de origem no ERP** ("Gerado pelo FabriQ em …");
   - PDF reflete exatamente o banco no momento da geração; **cada geração é um registro** (modelo `GeracaoDossie`: lote, usuário, data/hora, hash/arquivo);
   - anexos muito grandes: listar e vincular em vez de embutir (regra de tamanho configurável);
   - o banco continua sendo a fonte oficial — o PDF é evidência consolidada.
4. Testes: gerar dossiê de lote de teste e conferir todos os blocos + identificação de quando/por quem foi gerado.

### Critérios de aceite (PDF)
- A partir do pedido expedido, abrir o produto, selecionar um lote e visualizar o dossiê completo, com todos os links e exportação em PDF.
- Gerar o PDF de um lote de teste e conferir se contém todos os blocos e identifica quando e por quem foi gerado.

---

## Etapa 13 — Homologação: roteiro de aceite final (PDF 9) ✅ CONCLUÍDA (22/07/2026)

> **Status:** roteiro automatizado e documentado (334 testes do projeto passando).
> - **Caminho feliz:** `apps/core/tests_homologacao.py` executa os 14 passos de ponta a
>   ponta com dados fictícios, pelas mesmas telas e serviços do operador e com **um
>   usuário por perfil** (almoxarifado, qualidade, PCP, produção, expedição, diretoria) —
>   o roteiro também valida o modelo de permissões.
> - **Contraprova:** `apps/core/tests_violacoes.py` tenta furar cada bloqueio da lista
>   abaixo e confirma que o sistema recusa (13 testes, um por item).
> - **Para rodar com o cliente:** `docs/roteiro-homologacao.md` traz o passo a passo na
>   tela (o que fazer, onde clicar, resultado esperado), a tabela de violações e o
>   quadro de registro do aceite.
> - Observação sobre "em quarentena": o bloqueio é pelo **local** — o saldo em Quarentena
>   não é oferecido para apontamento. A situação `AGUARDANDO_CQ` em si não impede o
>   consumo; o que impede é vencimento, reprovação ou bloqueio.
>
> ```bash
> .venv/bin/python manage.py test apps.core.tests_homologacao apps.core.tests_violacoes
> ```

Executar com **dados fictícios**, sem depender de planilhas paralelas:

1. Cadastrar fornecedor, matéria-prima, embalagem, produto, fórmula e equipamento.
2. Receber materiais, criar lotes internos (geração automática — Etapa 2a) e registrar documentos.
3. Colocar em quarentena, analisar e liberar os lotes.
4. Criar pedido, programar a produção e emitir a OP.
5. Selecionar lotes específicos e registrar pesagem e dupla conferência.
6. Registrar equipamentos, limpeza, etapas, parâmetros e controles em processo.
7. Registrar envase, embalagens, perdas, desvios e quantidade final.
8. Gerar o lote acabado, realizar CQ final e liberar.
9. Expedir apenas o lote liberado.
10. Abrir o pedido expedido, clicar no produto e acessar o lote e o dossiê.
11. Abrir a OP, a fórmula, cada material, lote, fornecedor e documento relacionado.
12. Realizar rastreabilidade reversa a partir de um lote de matéria-prima.
13. Gerar o dossiê completo em PDF.
14. Conferir a trilha de auditoria de todas as ações e alterações.

**Bateria de testes de violação (PDF 7.2):** tentar violar cada bloqueio obrigatório e confirmar que o sistema impede a operação:
- [ ] Material sem fornecedor/lote/validade
- [ ] Lote vencido, em quarentena, reprovado ou bloqueado
- [ ] Fórmula alterada após emissão da OP
- [ ] OP concluída sem lotes, sem perdas ou sem quantidade final
- [ ] Liberação sem CQ
- [ ] Expedição de lote não liberado
- [ ] Balança com calibração vencida
- [ ] Equipamento bloqueado/sem limpeza
- [ ] Rótulo com versão de arte não aprovada
- [ ] Encerramento de OP com desvio pendente
- [ ] Exclusão/edição de registro de auditoria
- [ ] Lote interno digitado/alterado manualmente sem permissão e justificativa (Etapa 2a)

---

## Notas transversais

- **Perfis e permissões:** revisar `apps/accounts/perfis.py` a cada etapa — novas permissões: aprovar fórmula, autorizar exceção de bloqueio, decidir desvio, liberar CQ, liberação técnica, expedir, alterar lote interno manualmente.
- **Dados de demonstração:** atualizar `apps/core/management/commands/carregar_demo.py` a cada etapa para que o roteiro da Etapa 13 rode de ponta a ponta com dados fictícios.
- **Testes automatizados:** cada etapa entrega seus testes (`apps/*/tests.py`) cobrindo, no mínimo, o critério de aceite do PDF correspondente.
- **Imutabilidade:** seguir o padrão já usado em `Movimentacao` (correção = novo registro, nunca edição) para trilha, snapshot, pesagens, controles e gerações de dossiê.
- **O ERP não substitui POPs**, treinamentos, calibrações, análises ou decisões técnicas — ele orienta a execução, registra evidências, impede desvios críticos e organiza aprovações (PDF, seção 10).

**Responsável pela revisão funcional:** André Gustavo Dantas Máximo · **Desenvolvimento:** Jonatas

---

## Anexo A — Modelo de etiqueta de matéria-prima (referência do cliente, 18/07/2026) ✅ ATENDIDO (22/07/2026)

Layout livre — o modelo abaixo é **apenas base**; o conteúdo listado é o que deve constar (ver Etapa 2b).

> **Status:** implementado na Etapa 2b e conferido campo a campo em 22/07/2026 na tela
> `recebimento:etiqueta` (`templates/recebimento/etiqueta.html`). Todos os campos do modelo
> saem preenchidos a partir do banco — nada é digitado na etiqueta.

### Correspondência: modelo do cliente × origem no sistema

| Campo do Anexo A | De onde o sistema tira |
| --- | --- |
| Nome da Matéria-Prima | `ItemRecebimento.item.nome` (o título muda para Embalagem/Produto conforme o item) |
| Código Interno | `ItemRecebimento.item.codigo` |
| Fornecedor | `Recebimento.fornecedor` |
| Nº da Nota Fiscal | `Recebimento.nota_fiscal` |
| Lote do Fornecedor | `Lote.lote_fornecedor` (Etapa 2a) |
| Lote Interno | `Lote.codigo` — gerado automaticamente, sequencial (Etapa 2a) |
| Data de Recebimento | `Recebimento.data_recebimento` |
| Data de Validade | `Lote.validade` |
| Cliente | `Recebimento.cliente` — preenchido só em terceirização |
| STATUS | `ItemRecebimento.status` (`StatusQuarentena`), com “X” na situação atual |
| Data da Liberação CQ | última `DecisaoQuarentena` liberada do item |
| Responsável pela Liberação | `DecisaoQuarentena.responsavel` |
| Localização | `locais_do_lote(lote)` — locais com saldo positivo |

### Vocabulário do bloco STATUS

O sistema usa os termos do fluxo de quarentena, equivalentes aos do modelo:

| Modelo do cliente | Sistema | Observação |
| --- | --- | --- |
| QUARENTENA | Em quarentena | — |
| EM ANÁLISE | Em análise | criado na Etapa 2b para este modelo |
| APROVADO | **Liberado** | mesma decisão; “liberar” é o verbo usado em toda a quarentena |
| REJEITADO | **Reprovado** | mesma decisão |
| DEVOLVIDO | Devolvido | criado na Etapa 2b para este modelo |
| — | Bloqueado | situação extra do sistema, sem equivalente no modelo |

> Se a Corpo & Cheiro preferir imprimir exatamente “APROVADO/REJEITADO”, basta trocar os
> rótulos de `StatusQuarentena` — mas isso muda o texto em todas as telas de quarentena,
> não só na etiqueta.

### Além do modelo

- **Quantidade recebida** com unidade, para conferência física na prateleira.
- **Rodapé de origem**: “Gerada pelo FabriQ em `<data/hora>` · `REC-00001`”.
- Cada visualização/impressão grava um evento **IMPRESSAO** na trilha do lote (Etapa 1),
  permitindo identificar etiquetas impressas antes de uma decisão do CQ.

```
MATÉRIA-PRIMA

Nome da Matéria-Prima: _____________________________
Código Interno: ____________________________________
Fornecedor: ________________________________________
Nº da Nota Fiscal: _________________________________
Lote do Fornecedor: ________________________________
Lote Interno: ______________________________________
Data de Recebimento: __/__/____
Data de Validade: __/__/____
Cliente: ___________________________________________

STATUS
☐ QUARENTENA
☐ EM ANÁLISE
☐ APROVADO
☐ REJEITADO
☐ DEVOLVIDO

Data da Liberação CQ: __/__/____
Responsável pela Liberação: _________________________
Localização: _______________________________________
```
