# Cronograma de Desenvolvimento - ERP Industrial Corpo & Cheiro (Django)

> Planejamento do MVP baseado no briefing inicial do cliente, considerando uma estrutura enxuta e compatível com o orçamento disponível.

## Visão Geral

**Objetivo:** desenvolver um ERP industrial em Django para substituir planilhas e controles em papel, permitindo que a fábrica opere o fluxo produtivo em um único sistema.

## Stack inicial sugerida

- Python
- Django
- Django Templates
- Bootstrap
- PostgreSQL
- Docker, caso seja viável no servidor
- Nginx
- Gunicorn
- Armazenamento local de arquivos no servidor

## Ambientes

Nesta primeira etapa serão utilizados apenas:

- Ambiente local de desenvolvimento
- Ambiente de produção

Não será criado um ambiente separado de homologação neste momento.

A validação das funcionalidades será realizada inicialmente no ambiente local e, após aprovação, a versão será publicada em produção.

---

# Fase 0 – Levantamento e Estrutura Inicial

## Objetivos

- Revisar o fluxo atual da fábrica
- Validar as regras de negócio
- Definir prioridades do MVP
- Organizar os módulos e dependências
- Criar a estrutura inicial do projeto Django

## Entregáveis

- Projeto Django configurado
- Banco de dados PostgreSQL configurado
- Estrutura inicial dos aplicativos Django
- Configuração do ambiente local
- Configuração básica do ambiente de produção
- Layout inicial com Django Templates e Bootstrap
- Estrutura de logs
- Estrutura básica de auditoria

## Duração estimada

**1 semana**

---

# Fase 1 – Login e Controle de Usuários

## Funcionalidades

- Login
- Logout
- Recuperação de senha
- Cadastro de usuários
- Edição de usuários
- Usuários ativos e inativos
- Registro do último acesso
- Perfis de acesso:
  - Administrador
  - Diretoria
  - Produção
  - Qualidade
  - Almoxarifado
  - PCP
  - Compras
  - Expedição
- Controle de permissões por perfil

## Critério de aceite

Cada usuário deverá visualizar e acessar apenas os módulos permitidos para o seu perfil.

## Duração estimada

**1 semana**

---

# Fase 2 – Cadastros Gerais

## Cadastros

- Clientes
- Fornecedores
- Produtos
- Matérias-primas
- Embalagens
- Equipamentos
- Setores

## Funcionalidades comuns

- Cadastro
- Edição
- Consulta
- Paginação
- Pesquisa
- Filtros
- Ativação e inativação
- Registro de usuário, data e hora da alteração

## Critério de aceite

Todos os cadastros necessários para pedidos, estoque, qualidade e produção deverão estar disponíveis e relacionados corretamente.

## Duração estimada

**2 semanas**

---

# Fase 3 – Pedidos

## Funcionalidades

- Cadastro de pedidos
- Seleção do cliente
- Inclusão de produtos
- Quantidades
- Prazo
- Observações
- Consulta e filtros
- Histórico de alterações
- Controle de status

## Fluxo de status

```text
Recebido
↓
Em análise
↓
Aguardando MP
↓
Programado
↓
Em produção
↓
CQ
↓
Finalizado
↓
Expedido
```

## Regras

- O pedido deve possuir cliente e pelo menos um produto.
- Alterações importantes devem ser registradas no histórico.
- Um pedido não poderá avançar sem cumprir as regras da etapa atual.

## Duração estimada

**2 semanas**

---

# Fase 4 – PCP

## Funcionalidades

- Programação da produção
- Visualização por calendário
- Definição de equipamentos
- Definição de capacidade
- Definição de operadores
- Filtros por período
- Filtros por equipamento
- Filtros por produto
- Filtros por status
- Reprogramação da produção

## Critério de aceite

O setor de PCP deverá conseguir organizar os pedidos programados e visualizar a ocupação dos equipamentos.

## Duração estimada

**2 semanas**

---

# Fase 5 – Estoque

## Funcionalidades

- Entrada de materiais
- Saída de materiais
- Transferência entre locais
- Inventário
- Ajustes de estoque
- Localização física
- Controle por lote
- Controle de validade
- Consulta de saldo
- Histórico de movimentações

## Regras

Toda movimentação deverá registrar:

- Usuário
- Data
- Hora
- Tipo de movimentação
- Quantidade
- Motivo
- Lote
- Origem e destino, quando aplicável

## Duração estimada

**2 semanas**

---

# Fase 6 – Recebimento e Quarentena

## Recebimento

- Registro da Nota Fiscal
- Fornecedor
- Produto ou matéria-prima
- Lote
- Validade
- Quantidade
- Anexo de COA
- Anexo de FISPQ
- Fotos
- Observações
- Entrada automática em quarentena

## Quarentena

- Aprovação
- Reprovação
- Bloqueio
- Liberação
- Registro do responsável
- Registro de observações
- Histórico da decisão

## Critério de aceite

Nenhum material recebido poderá ficar disponível para produção antes da liberação pela área responsável.

## Duração estimada

**2 semanas**

---

# Fase 7 – Controle de Qualidade

## Funcionalidades

- Cadastro de análises
- Tipos de análise
- Registro de resultados
- Valores de referência
- Anexos
- Observações
- Aprovação
- Reprovação
- Histórico

## Critério de aceite

O sistema deverá permitir registrar os resultados de qualidade e controlar a liberação ou reprovação de materiais e produtos.

## Duração estimada

**1 semana**

---

# Fase 8 – Ordem de Produção

## Funcionalidades

- Geração da Ordem de Produção
- Vínculo com o pedido
- Seleção da fórmula
- Seleção do equipamento
- Seleção do operador
- Materiais necessários
- Quantidades previstas
- Data programada
- Status da OP
- Impressão ou visualização da OP
- Histórico

## Regras

A Ordem de Produção somente poderá ser liberada quando houver:

- Pedido aprovado
- Matéria-prima liberada
- Estoque suficiente
- Equipamento definido
- Operador definido

## Duração estimada

**2 semanas**

---

# Fase 9 – Produção

## Funcionalidades

- Início da produção
- Finalização da produção
- Registro de operador
- Registro de equipamento
- Quantidade produzida
- Perdas
- Tempo de produção
- Ocorrências
- Paradas
- Motivos de parada
- Fotos
- Observações
- Histórico

## Critério de aceite

A equipe de produção deverá conseguir registrar todo o processo produtivo e concluir a Ordem de Produção.

## Duração estimada

**2 semanas**

---

# Fase 10 – Dashboard

## Indicadores iniciais

- Pedidos em andamento
- Produção do dia
- Materiais em quarentena
- Estoque crítico
- Pedidos atrasados
- Ordens de Produção abertas
- Alertas operacionais

## Observação

O dashboard inicial será desenvolvido com recursos do próprio Django, HTML, Bootstrap e bibliotecas JavaScript leves para gráficos, sem utilização de React.

## Duração estimada

**1 semana**

---

# Fase 11 – Testes e Ajustes

## Atividades

- Testes dos fluxos principais
- Testes de permissões
- Testes das regras de negócio
- Testes de estoque
- Testes de aprovação e reprovação
- Testes da Ordem de Produção
- Correção de erros
- Ajustes solicitados pelo cliente
- Validação dos usuários responsáveis

## Observação

Como não haverá ambiente de homologação separado, os testes serão realizados no ambiente local com dados de teste antes da publicação em produção.

## Duração estimada

**1 semana**

---

# Fase 12 – Implantação e Treinamento

## Atividades

- Configuração do servidor de produção
- Configuração do PostgreSQL
- Configuração do Gunicorn
- Configuração do Nginx
- Configuração de domínio e HTTPS, caso disponíveis
- Publicação do sistema
- Criação dos usuários iniciais
- Cadastro de dados básicos
- Treinamento dos usuários
- Entrega de manual simplificado
- Acompanhamento inicial

## Duração estimada

**1 semana**

---

# Regras Obrigatórias do Sistema

Nenhum lote poderá ser produzido sem:

- Pedido aprovado
- Ordem de Produção emitida
- Matéria-prima liberada
- Estoque suficiente

Todas as movimentações deverão registrar:

- Usuário
- Data
- Hora
- Motivo

Os registros não deverão ser excluídos definitivamente.

Sempre que possível, será utilizada inativação ou cancelamento com registro do motivo.

---

# Estrutura sugerida dos Apps Django

```text
core
accounts
cadastros
clientes
fornecedores
produtos
materias_primas
equipamentos
pedidos
pcp
estoque
recebimento
quarentena
qualidade
ordens_producao
producao
dashboard
auditoria
```

A quantidade de aplicativos poderá ser reduzida ou reorganizada durante o desenvolvimento para evitar complexidade desnecessária.

---

# Estimativa Geral

| Fase | Duração estimada |
|---|---:|
| Levantamento e estrutura inicial | 1 semana |
| Login e usuários | 1 semana |
| Cadastros gerais | 2 semanas |
| Pedidos | 2 semanas |
| PCP | 2 semanas |
| Estoque | 2 semanas |
| Recebimento e quarentena | 2 semanas |
| Controle de qualidade | 1 semana |
| Ordem de Produção | 2 semanas |
| Produção | 2 semanas |
| Dashboard | 1 semana |
| Testes e ajustes | 1 semana |
| Implantação e treinamento | 1 semana |

**Total estimado:** aproximadamente **20 semanas** para entrega do MVP.

O prazo poderá variar conforme:

- Disponibilidade do cliente para validar os módulos
- Clareza das regras de negócio
- Quantidade de alterações durante o desenvolvimento
- Qualidade dos dados existentes
- Necessidade de importação de planilhas
- Infraestrutura disponível para produção

---

# Itens Fora do Escopo Inicial

Os itens abaixo não fazem parte da primeira versão, mas o sistema será organizado para permitir inclusão futura:

- React
- Aplicativo mobile
- Ambiente separado de homologação
- Arquitetura com múltiplos servidores
- Kubernetes
- Pipeline avançado de CI/CD
- Redis
- Celery
- MinIO ou armazenamento S3
- Integração com balanças
- Integração com leitores de código de barras
- QR Code
- Integração com ERP financeiro
- Integração com emissão fiscal
- Business Intelligence
- Aplicativo para coletores
- Notificações em tempo real
- API pública para terceiros

Esses requisitos poderão ser adicionados posteriormente, caso a empresa tenha necessidade e orçamento para novas etapas.

---

# Estratégia de Entrega

O projeto deverá ser entregue de forma incremental.

Ao final de cada fase:

1. O módulo será apresentado ao cliente.
2. As regras serão validadas.
3. Serão registrados os ajustes necessários.
4. A próxima fase será iniciada após a validação do fluxo principal.

Essa abordagem reduz retrabalho e permite que o cliente acompanhe a evolução do sistema durante todo o desenvolvimento.
