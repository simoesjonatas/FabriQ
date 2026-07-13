# FabriQ

ERP industrial para o controle do fluxo produtivo — pedidos, PCP, estoque,
recebimento/quarentena, qualidade e produção em um único sistema.

Cliente: **Corpo & Cheiro** · Planejamento completo em
[Cronograma de Desenvolvimento](Cronograma_Desenvolvimento_ERP_Corpo_e_Cheiro_Django_Ajustado.md).

## Stack

- Python 3.14 · Django 5.2 LTS
- Django Templates + Bootstrap 5 (servido localmente, sem CDN)
- SQLite no desenvolvimento · PostgreSQL em produção
- Gunicorn + Nginx Proxy Manager em produção

## Ambiente local

```bash
# 1. Ambiente virtual e dependências
python3 -m venv .venv
.venv/bin/pip install -r requirements/local.txt

# 2. Variáveis de ambiente
cp .env.example .env   # gere uma DJANGO_SECRET_KEY nova

# 3. Banco e usuário inicial
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser

# 4. Servidor de desenvolvimento
.venv/bin/python manage.py runserver
```

O desenvolvimento usa SQLite por padrão (sem configuração). Para usar
PostgreSQL local, suba o banco com `docker compose up -d` e descomente o
`DATABASE_URL` no `.env` (porta 5433 para não conflitar com outros bancos).

## Produção com Docker

O deploy de produção sobe a aplicação e o PostgreSQL. O certificado HTTPS fica
no Nginx Proxy Manager apontando para o container `fabriq_web`.

```bash
# 1. Configure os segredos e o domínio
cp .env.production.example .env.production

# 2. Suba banco + aplicação
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

# 3. Crie o usuário administrador inicial
docker compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

No Nginx Proxy Manager, crie um **Proxy Host**:

- Domain Names: `fabriq.simoesti.com.br`
- Scheme: `http`
- Forward Hostname/IP: `fabriq_web` se o NPM estiver na network `fabriq_proxy`; ou o IP do servidor se for proxy pela porta publicada
- Forward Port: `8000`
- SSL: solicite um certificado Let's Encrypt, ative `Force SSL` e `HTTP/2 Support`

Se o domínio ficar em loop de redirecionamento, adicione em **Advanced** no NPM:

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
```

Se o NPM estiver em outro Compose, conecte o container dele à network do FabriQ:

```bash
docker network connect fabriq_proxy nome-do-container-do-nginx-proxy-manager
```

Antes de emitir o certificado, o DNS de `fabriq.simoesti.com.br` precisa apontar
para o IP público do servidor.

## Comandos úteis

```bash
.venv/bin/python manage.py test        # roda os testes
.venv/bin/ruff check .                 # linter
.venv/bin/python manage.py check       # checagens do Django
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f web
```

## Estrutura

```
config/            # settings (base/local/production), urls, wsgi
apps/
  core/            # modelos base (auditoria, ativo/inativo), página inicial
  accounts/        # usuário customizado, perfis de acesso (Fase 1)
templates/         # base.html + templates por app
static/            # css próprio + Bootstrap vendorizado
requirements/      # base / local / production
logs/              # arquivos de log (produção)
```

## Convenções do projeto

- **Nada é excluído definitivamente**: cadastros usam o campo `ativo`
  (herdado de `core.ModeloBase`); operações usam cancelamento com motivo.
- **Toda alteração registra usuário, data e hora** (`core.ModeloAuditado`).
- Logs da aplicação usam `logging.getLogger("fabriq")`.
- Código de domínio em português (modelos, campos, templates).
- Cada fase só começa após a validação da anterior (entrega incremental).
