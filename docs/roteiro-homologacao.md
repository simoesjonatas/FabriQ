# Roteiro de homologação do FabriQ

Roteiro de aceite final da Etapa 13 (PDF de complementação funcional, seção 9),
para ser executado **na tela, junto com a Corpo & Cheiro**.

> ⚠️ **Sempre com dados fictícios.** A fábrica está em interdição sanitária;
> nenhum dado real de produção entra no sistema durante a homologação.

O mesmo roteiro roda automatizado em `apps/core/tests_homologacao.py`
(caminho feliz) e `apps/core/tests_violacoes.py` (bateria de bloqueios).
Rodar antes da reunião:

```bash
.venv/bin/python manage.py test apps.core.tests_homologacao apps.core.tests_violacoes
```

---

## Preparação

1. Carregar a base de demonstração (apaga e recria os dados fictícios):

```bash
.venv/bin/python manage.py carregar_demo --recarregar
```

2. Subir o servidor e abrir `http://127.0.0.1:8000/`.

3. Usuários da demonstração — senha **`fabriq.demo`** para todos:

| Usuário | Papel | Usa no roteiro |
| --- | --- | --- |
| `jose.almoxarife` | Almoxarifado | recebimento, estoque |
| `paula.qualidade` | Qualidade | quarentena, CQ, desvios |
| `ana.pcp` | PCP | pedido, programação, OP |
| `marcos.producao` | Produção | execução, pesagem, envase |
| `rita.expedicao` | Expedição | expedição |
| `diretor` | Diretoria | dossiê, visão geral |

---

## Parte 1 — Ciclo completo (14 passos)

Marque cada passo conforme for validando com o cliente.

### 1. Cadastros
- [ ] **Cadastros** → cadastrar/conferir fornecedor, matéria-prima, embalagem,
      produto, fórmula, equipamento e balança.
- **Esperado:** produto com situação regulatória e fórmula com versão **v1 vigente**.

### 2. Recebimento com lote interno automático
- [ ] Entrar como `jose.almoxarife` → **Recebimento** → *Novo recebimento*.
- [ ] Informar fornecedor, NF, itens, **lote do fornecedor** e validade.
- **Esperado:** o **lote interno é gerado pelo sistema** (`MP-AAAA-NNNNN`), o lote do
      fornecedor fica gravado ao lado, e entra saldo automático em **Quarentena**.
- [ ] Abrir a **etiqueta** do item (botão na tela do recebimento) e conferir contra o
      Anexo A: nome, código, fornecedor, NF, os dois lotes, datas, status e localização.

### 3. Quarentena, análise e liberação
- [ ] Entrar como `paula.qualidade` → **Quarentena** → decidir o item.
- [ ] Liberar informando o local de destino.
- **Esperado:** situação do lote vai para **Aprovado**, o saldo **transfere** da
      Quarentena para o almoxarifado, e a decisão fica na trilha do lote.

### 4. Pedido, programação e OP
- [ ] Entrar como `ana.pcp` → **Pedidos** → novo pedido do cliente.
- [ ] Avançar para *Em análise* → *Programado*; programar no **PCP**.
- [ ] **Ordens de produção** → emitir a OP (item do pedido + fórmula + equipamento +
      linha + operador + supervisor) e depois **Liberar**.
- **Esperado:** ao liberar, o sistema **congela a fórmula** (snapshot com a versão) e
      **reserva o lote do produto acabado**. A OP mostra a versão congelada.

### 5. Lotes específicos e pesagem com dupla conferência
- [ ] Como `marcos.producao` → **Produção** → *Apontar lotes*: escolher os lotes.
- [ ] *Pesagem*: registrar com **operador e conferente diferentes**.
- **Esperado:** o consumo fica amarrado ao lote escolhido; material crítico **exige**
      o conferente; fora da tolerância o sistema recusa.

### 6. Equipamento, etapas e controle em processo
- [ ] Registrar o **checklist do equipamento** (pré-uso).
- [ ] *Etapas*: registrar na sequência da fórmula, com temperatura/tempo/velocidade.
- [ ] *Controles*: registrar o parâmetro (ex.: pH) — o limite vem da **especificação
      do produto**.
- **Esperado:** etapa fora de ordem é recusada; pular etapa exige justificativa;
      resultado fora do limite é marcado como **fora de especificação**.

### 7. Envase, perdas e desvios
- [ ] *Envase*: registrar com a **versão de arte aprovada**.
- [ ] *Desvios*: abrir um desvio e pedir para a Qualidade decidir.
- [ ] Concluir a produção informando **quantidade final e perdas**.
- **Esperado:** perda acima do limite do produto exige justificativa e aprovação;
      **desvio pendente impede encerrar a OP**.

### 8. Lote acabado, CQ final e liberação
- **Esperado após concluir:** lote acabado criado com entrada no estoque e situação
      **Aguardando CQ**.
- [ ] Como `paula.qualidade` → **Qualidade** → lançar resultados e **Aprovar**.
- **Esperado:** a decisão do CQ muda a situação do lote para **Aprovado**.
- [ ] Conferir as **assinaturas por fase** na tela da OP (quem fez o quê e quando).

### 9. Expedição só do lote liberado
- [ ] Como `rita.expedicao` → **Expedição** → expedir o pedido finalizado.
- [ ] Selecionar o lote aprovado, quantidade, NF e transportadora.
- **Esperado:** só aparecem **lotes aprovados**; a expedição **baixa o estoque**, o
      lote vai para **Expedido** e o pedido só então pode ir para *Expedido*.
- [ ] Expedir **parcialmente** e conferir que o **saldo pendente** continua no pedido.

### 10 e 11. Navegação por links (do pedido ao fornecedor)
- [ ] Abrir o **pedido expedido** e conferir, por item: pedida, produzida, aprovada,
      expedida e saldo, com as **OPs e lotes** que atenderam.
- [ ] Clicar no **cliente** → ficha do cliente (documentos com alerta de vencimento).
- [ ] Clicar no **produto** → ficha (fórmulas, artes, especificações, OPs, lotes).
- [ ] Clicar no **lote** → ficha do lote → **OP** → **material** → **lote da MP** →
      **fornecedor / recebimento / NF / análise**.
- **Esperado:** dá para percorrer a cadeia inteira **sem nova pesquisa**.

### 12. Rastreabilidade nos dois sentidos
- [ ] **Estoque → Rastreabilidade**: buscar por **lote do fornecedor** (ex.: `ALOE-77`).
- [ ] *Para onde foi*: OPs que consumiram, lotes acabados, quantidades e **clientes**.
- [ ] *De onde veio* (a partir do lote acabado): OP, fórmula congelada, cada material
      com lote, fornecedor, NF, consumo e saldo, e **quem recebeu**.
- **Esperado:** responde às três perguntas: de onde veio, quais lotes usam a MP X e
      quais clientes receberam (recolhimento).

### 13. Dossiê do lote + PDF
- [ ] Abrir o **dossiê** do lote (botão no pedido, na ficha do produto, no lote ou na OP).
- [ ] Conferir os blocos: identificação, fórmula (teórico × pesado), materiais com
      documentos, pesagens, equipamentos, etapas, controles, envase, perdas, desvios,
      liberações, CQ, expedições e trilha.
- [ ] **Gerar PDF** e conferir o rodapé: *“Gerado pelo FabriQ em … por …”*, código do
      dossiê, versão e paginação.
- **Esperado:** cada geração vira um **registro** (versão, autor, data/hora e hash),
      listado na própria tela.

### 14. Trilha de auditoria
- [ ] Conferir a trilha no lote, na OP, no pedido e na fórmula.
- **Esperado:** alterações de campos críticos aparecem com **valor anterior → novo,
      autor, data e justificativa**. Nada pode ser editado ou apagado.

---

## Parte 2 — Bateria de violações (PDF 7.2)

Tentar furar cada bloqueio **na tela** e confirmar que o sistema recusa.
Todos já são cobertos por teste automatizado em `apps/core/tests_violacoes.py`.

| # | Tentativa | O sistema deve |
| --- | --- | --- |
| 1 | Concluir OP com material sem lote apontado | recusar e pedir o apontamento |
| 2 | Consumir lote **vencido**, **reprovado** ou **bloqueado** | recusar (só com exceção justificada por perfil autorizado) |
| 2b | Consumir material ainda **em Quarentena** | não oferecer o saldo para apontamento |
| 3 | Alterar a fórmula **depois** de emitir a OP | criar **nova versão**; a OP mantém a versão congelada |
| 4 | Concluir OP sem quantidade final | recusar |
| 5 | Liberar/expedir **sem CQ** | recusar |
| 6 | Expedir lote **não liberado** | recusar |
| 7 | Pesar em balança com **calibração vencida** | recusar |
| 8 | Liberar OP com equipamento **sem limpeza** ou **interditado** | recusar |
| 9 | Envasar com **arte não aprovada** / rótulo com arte obsoleta | recusar |
| 10 | Encerrar OP com **desvio pendente** | recusar |
| 11 | Editar ou excluir registro de **auditoria** | recusar (imutável) |
| 12 | Alterar o **lote interno** sem justificativa | exigir justificativa e gravar na trilha |

---

## Registro do aceite

| Item | Resultado | Observações |
| --- | --- | --- |
| Parte 1 — ciclo completo (14 passos) | ☐ Aprovado ☐ Com ressalvas | |
| Parte 2 — bateria de violações (13 itens) | ☐ Aprovado ☐ Com ressalvas | |

**Data:** ___/___/______  
**Pela Corpo & Cheiro:** ______________________________  
**Revisão funcional:** André Gustavo Dantas Máximo  
**Desenvolvimento:** Jonatas

> Lembrete do PDF (seção 10): o ERP **não substitui** POPs, treinamentos, calibrações,
> análises ou decisões técnicas — ele orienta a execução, registra evidências, impede
> desvios críticos e organiza aprovações.
