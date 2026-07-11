from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cadastros.models import (
    Cliente,
    ClienteEndereco,
    ClienteTelefone,
    Embalagem,
    Equipamento,
    Fornecedor,
    FornecedorEndereco,
    FornecedorTelefone,
    MateriaPrima,
    Produto,
    Setor,
    TipoEmbalagem,
    Unidade,
)


class Command(BaseCommand):
    help = "Popula cadastros de demonstracao para visualizar melhor as telas."

    def handle(self, *args, **options):
        with transaction.atomic():
            totais = {
                "setores": self._setores(),
                "clientes": self._clientes(),
                "fornecedores": self._fornecedores(),
                "produtos": self._produtos(),
                "materias_primas": self._materias_primas(),
                "embalagens": self._embalagens(),
                "equipamentos": self._equipamentos(),
            }

        resumo = ", ".join(f"{nome}: {total}" for nome, total in totais.items())
        self.stdout.write(self.style.SUCCESS(f"Cadastros demo prontos ({resumo})."))

    def _setores(self):
        dados = [
            {
                "nome": "Pesagem",
                "descricao": "Separacao e conferencia dos insumos antes da producao.",
                "ativo": True,
            },
            {
                "nome": "Manipulacao",
                "descricao": "Preparo de bases, cremes, loções e concentrados.",
                "ativo": True,
            },
            {
                "nome": "Envase",
                "descricao": "Envase, fechamento e rotulagem dos produtos acabados.",
                "ativo": True,
            },
            {
                "nome": "Qualidade",
                "descricao": "Inspecao de amostras, liberacao e quarentena.",
                "ativo": True,
            },
            {
                "nome": "Linha antiga",
                "descricao": "Setor legado mantido apenas para historico.",
                "ativo": False,
            },
        ]
        return self._update_por_chave(Setor, "nome", dados)

    def _clientes(self):
        dados = [
            {
                "razao_social": "Studio Belle Comercio de Cosmeticos LTDA",
                "nome_fantasia": "Studio Belle",
                "documento": "18745233000189",
                "email": "compras@studiobelle.com.br",
                "telefone": "(11) 3388-1290",
                "telefones": [
                    {"tipo": "COMERCIAL", "telefone": "(11) 3388-1290", "principal": True},
                    {"tipo": "FINANCEIRO", "telefone": "(11) 3388-1291", "contato": "Financeiro"},
                ],
                "endereco": "Rua Harmonia, 145",
                "cidade": "Sao Paulo",
                "uf": "SP",
                "cep": "05435-000",
                "enderecos": [
                    {
                        "tipo": "COMERCIAL",
                        "logradouro": "Rua Harmonia",
                        "numero": "145",
                        "bairro": "Vila Madalena",
                        "cidade": "Sao Paulo",
                        "uf": "SP",
                        "cep": "05435-000",
                        "principal": True,
                    },
                    {
                        "tipo": "ENTREGA",
                        "logradouro": "Rua Girassol",
                        "numero": "820",
                        "bairro": "Vila Madalena",
                        "cidade": "Sao Paulo",
                        "uf": "SP",
                        "cep": "05433-002",
                    },
                ],
                "observacoes": "Cliente recorrente de kits de hidratacao.",
                "ativo": True,
            },
            {
                "razao_social": "Aroma Sul Distribuidora SA",
                "nome_fantasia": "Aroma Sul",
                "documento": "04231765000193",
                "email": "pedidos@aromasul.com.br",
                "telefone": "(51) 3030-4400",
                "endereco": "Av. Ipiranga, 8200",
                "cidade": "Porto Alegre",
                "uf": "RS",
                "cep": "91530-000",
                "observacoes": "Distribuidora com pedidos mensais.",
                "ativo": True,
            },
            {
                "razao_social": "Drogaria Primavera LTDA",
                "nome_fantasia": "Primavera Farma",
                "documento": "31509048000153",
                "email": "suprimentos@primaverafarma.com.br",
                "telefone": "(31) 3290-7788",
                "endereco": "Av. do Contorno, 3120",
                "cidade": "Belo Horizonte",
                "uf": "MG",
                "cep": "30110-017",
                "observacoes": "Prioriza embalagens de 250 ml.",
                "ativo": True,
            },
            {
                "razao_social": "Emporio Natural do Vale ME",
                "nome_fantasia": "Natural do Vale",
                "documento": "22734991000179",
                "email": "contato@naturaldovale.com.br",
                "telefone": "(12) 3942-1122",
                "endereco": "Rua das Acacias, 80",
                "cidade": "Sao Jose dos Campos",
                "uf": "SP",
                "cep": "12245-000",
                "observacoes": "Compra linhas veganas e sem fragrancia.",
                "ativo": True,
            },
            {
                "razao_social": "Rede Harmonia Cosméticos EIRELI",
                "nome_fantasia": "Harmonia Beauty",
                "documento": "16900344000197",
                "email": "financeiro@harmoniabeauty.com.br",
                "telefone": "(21) 3555-9090",
                "endereco": "Rua Voluntarios da Patria, 420",
                "cidade": "Rio de Janeiro",
                "uf": "RJ",
                "cep": "22270-010",
                "observacoes": "Cadastro inativo para visualizacao de filtro.",
                "ativo": False,
            },
        ]
        return self._update_pessoas_por_documento(
            Cliente, ClienteTelefone, ClienteEndereco, "cliente", dados
        )

    def _fornecedores(self):
        dados = [
            {
                "razao_social": "Essencia Brasil Ingredientes LTDA",
                "nome_fantasia": "Essencia Brasil",
                "documento": "09012654000100",
                "email": "vendas@essenciabrasil.com.br",
                "telefone": "(11) 4602-7800",
                "telefones": [
                    {"tipo": "COMERCIAL", "telefone": "(11) 4602-7800", "principal": True},
                    {"tipo": "CELULAR", "telefone": "(11) 94602-7801", "contato": "Consultor"},
                ],
                "cidade": "Barueri",
                "uf": "SP",
                "enderecos": [
                    {
                        "tipo": "COMERCIAL",
                        "logradouro": "Alameda Madeira",
                        "numero": "222",
                        "bairro": "Alphaville",
                        "cidade": "Barueri",
                        "uf": "SP",
                        "cep": "06454-010",
                        "principal": True,
                    }
                ],
                "observacoes": "Fragrancias, oleos essenciais e conservantes.",
                "ativo": True,
            },
            {
                "razao_social": "Quimica Pura Industria e Comercio SA",
                "nome_fantasia": "Quimica Pura",
                "documento": "58234976000109",
                "email": "atendimento@quimicapura.com.br",
                "telefone": "(19) 3772-6000",
                "cidade": "Campinas",
                "uf": "SP",
                "observacoes": "Tensoativos, bases e insumos de alto giro.",
                "ativo": True,
            },
            {
                "razao_social": "Packline Embalagens Plasticas LTDA",
                "nome_fantasia": "Packline",
                "documento": "41127688000152",
                "email": "comercial@packline.com.br",
                "telefone": "(47) 3331-2200",
                "cidade": "Blumenau",
                "uf": "SC",
                "observacoes": "Frascos, tampas e valvulas.",
                "ativo": True,
            },
            {
                "razao_social": "Graficolor Rotulos Especiais LTDA",
                "nome_fantasia": "Graficolor",
                "documento": "74321560000184",
                "email": "orcamentos@graficolor.com.br",
                "telefone": "(41) 3220-8820",
                "cidade": "Curitiba",
                "uf": "PR",
                "observacoes": "Rotulos BOPP e cartuchos promocionais.",
                "ativo": True,
            },
            {
                "razao_social": "Fornecedor Legado Cosmopack LTDA",
                "nome_fantasia": "Cosmopack Legado",
                "documento": "66341092000181",
                "email": "contato@cosmopacklegado.com.br",
                "telefone": "(11) 2110-4500",
                "cidade": "Guarulhos",
                "uf": "SP",
                "observacoes": "Inativo para exemplo de situacao.",
                "ativo": False,
            },
        ]
        return self._update_pessoas_por_documento(
            Fornecedor, FornecedorTelefone, FornecedorEndereco, "fornecedor", dados
        )

    def _produtos(self):
        dados = [
            {
                "codigo": "PA-001",
                "nome": "Sabonete liquido erva doce 250 ml",
                "descricao": "Linha banho diario Corpo & Cheiro.",
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("180.000"),
                "observacoes": "Produto de alto giro.",
                "ativo": True,
            },
            {
                "codigo": "PA-002",
                "nome": "Hidratante corporal lavanda 500 ml",
                "descricao": "Creme corporal com fragrancia lavanda.",
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("120.000"),
                "observacoes": "Usado em kits promocionais.",
                "ativo": True,
            },
            {
                "codigo": "PA-003",
                "nome": "Shampoo nutritivo argan 300 ml",
                "descricao": "Linha cabelo e tratamento.",
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("150.000"),
                "observacoes": "",
                "ativo": True,
            },
            {
                "codigo": "PA-004",
                "nome": "Condicionador nutritivo argan 300 ml",
                "descricao": "Produto par do shampoo nutritivo.",
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("150.000"),
                "observacoes": "",
                "ativo": True,
            },
            {
                "codigo": "PA-005",
                "nome": "Creme para maos castanha 80 g",
                "descricao": "Linha cuidado diario.",
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("90.000"),
                "observacoes": "SKU compacto para checkout.",
                "ativo": True,
            },
            {
                "codigo": "PA-099",
                "nome": "Body splash flor de laranjeira 200 ml",
                "descricao": "Produto descontinuado.",
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("0.000"),
                "observacoes": "Inativo para historico.",
                "ativo": False,
            },
        ]
        return self._update_por_chave(Produto, "codigo", dados)

    def _materias_primas(self):
        dados = [
            {
                "codigo": "MP-ALOE",
                "nome": "Extrato glicolico de aloe vera",
                "unidade": Unidade.LITRO,
                "estoque_minimo": Decimal("35.000"),
                "observacoes": "Materia-prima sensivel a luz.",
                "ativo": True,
            },
            {
                "codigo": "MP-BASE-CREME",
                "nome": "Base creme hidratante neutra",
                "unidade": Unidade.QUILOGRAMA,
                "estoque_minimo": Decimal("220.000"),
                "observacoes": "Base comum para hidratantes.",
                "ativo": True,
            },
            {
                "codigo": "MP-TENSO-ANF",
                "nome": "Tensoativo anfotero",
                "unidade": Unidade.QUILOGRAMA,
                "estoque_minimo": Decimal("180.000"),
                "observacoes": "Usado em sabonetes liquidos e shampoos.",
                "ativo": True,
            },
            {
                "codigo": "MP-FRAG-LAV",
                "nome": "Fragrancia lavanda premium",
                "unidade": Unidade.LITRO,
                "estoque_minimo": Decimal("18.000"),
                "observacoes": "Requer aprovacao de qualidade por lote.",
                "ativo": True,
            },
            {
                "codigo": "MP-OLEO-ARG",
                "nome": "Oleo de argan cosmético",
                "unidade": Unidade.LITRO,
                "estoque_minimo": Decimal("24.000"),
                "observacoes": "Insumo importado.",
                "ativo": True,
            },
            {
                "codigo": "MP-CONS-OLD",
                "nome": "Conservante versao anterior",
                "unidade": Unidade.QUILOGRAMA,
                "estoque_minimo": Decimal("0.000"),
                "observacoes": "Substituido por nova formulacao.",
                "ativo": False,
            },
        ]
        return self._update_por_chave(MateriaPrima, "codigo", dados)

    def _embalagens(self):
        dados = [
            {
                "codigo": "EMB-FR-250",
                "nome": "Frasco PET transparente 250 ml",
                "tipo": TipoEmbalagem.FRASCO,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("1200.000"),
                "observacoes": "Usado na linha de sabonetes.",
                "ativo": True,
            },
            {
                "codigo": "EMB-FR-300",
                "nome": "Frasco PET ambar 300 ml",
                "tipo": TipoEmbalagem.FRASCO,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("900.000"),
                "observacoes": "Usado em shampoo e condicionador.",
                "ativo": True,
            },
            {
                "codigo": "EMB-VALV-28",
                "nome": "Valvula pump branca rosca 28",
                "tipo": TipoEmbalagem.VALVULA,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("800.000"),
                "observacoes": "",
                "ativo": True,
            },
            {
                "codigo": "EMB-TMP-24",
                "nome": "Tampa flip-top 24 mm natural",
                "tipo": TipoEmbalagem.TAMPA,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("1000.000"),
                "observacoes": "",
                "ativo": True,
            },
            {
                "codigo": "EMB-ROT-SAB",
                "nome": "Rotulo sabonete erva doce",
                "tipo": TipoEmbalagem.ROTULO,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("1500.000"),
                "observacoes": "Arte aprovada pelo cliente.",
                "ativo": True,
            },
            {
                "codigo": "EMB-CX-KIT",
                "nome": "Caixa kit presente kraft",
                "tipo": TipoEmbalagem.CAIXA,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("300.000"),
                "observacoes": "Sazonal.",
                "ativo": True,
            },
            {
                "codigo": "EMB-FR-OLD",
                "nome": "Frasco linha antiga 200 ml",
                "tipo": TipoEmbalagem.FRASCO,
                "unidade": Unidade.UNIDADE,
                "estoque_minimo": Decimal("0.000"),
                "observacoes": "Modelo fora de linha.",
                "ativo": False,
            },
        ]
        return self._update_por_chave(Embalagem, "codigo", dados)

    def _equipamentos(self):
        setores = {setor.nome: setor for setor in Setor.objects.all()}
        dados = [
            {
                "codigo": "EQ-BAL-01",
                "nome": "Balanca plataforma 300 kg",
                "setor": setores["Pesagem"],
                "capacidade": Decimal("300.000"),
                "unidade_capacidade": "kg",
                "observacoes": "Calibracao semestral.",
                "ativo": True,
            },
            {
                "codigo": "EQ-REATOR-01",
                "nome": "Reator inox 500 L",
                "setor": setores["Manipulacao"],
                "capacidade": Decimal("500.000"),
                "unidade_capacidade": "L/lote",
                "observacoes": "Agitacao com controle de temperatura.",
                "ativo": True,
            },
            {
                "codigo": "EQ-MIST-02",
                "nome": "Misturador alto cisalhamento",
                "setor": setores["Manipulacao"],
                "capacidade": Decimal("250.000"),
                "unidade_capacidade": "kg/lote",
                "observacoes": "",
                "ativo": True,
            },
            {
                "codigo": "EQ-ENV-01",
                "nome": "Linha de envase semiautomatica",
                "setor": setores["Envase"],
                "capacidade": Decimal("1800.000"),
                "unidade_capacidade": "un/h",
                "observacoes": "Atende frascos de 80 ml a 500 ml.",
                "ativo": True,
            },
            {
                "codigo": "EQ-LAB-01",
                "nome": "Viscosimetro digital",
                "setor": setores["Qualidade"],
                "capacidade": Decimal("1.000"),
                "unidade_capacidade": "amostra",
                "observacoes": "Usado em liberacao de lotes.",
                "ativo": True,
            },
            {
                "codigo": "EQ-OLD-01",
                "nome": "Envasadora manual antiga",
                "setor": setores["Linha antiga"],
                "capacidade": Decimal("120.000"),
                "unidade_capacidade": "un/h",
                "observacoes": "Inativa para exemplo de historico.",
                "ativo": False,
            },
        ]
        return self._update_por_chave(Equipamento, "codigo", dados)

    def _update_pessoas_por_documento(
        self, model, telefone_model, endereco_model, nome_parent, dados
    ):
        total = 0
        for item in dados:
            valores = item.copy()
            documento = valores.pop("documento")
            telefone_legado = valores.pop("telefone", "")
            endereco_legado = valores.pop("endereco", "")
            cidade_legada = valores.pop("cidade", "")
            uf_legada = valores.pop("uf", "")
            cep_legado = valores.pop("cep", "")
            telefones = valores.pop("telefones", None)
            enderecos = valores.pop("enderecos", None)

            pessoa, _criado = model.objects.update_or_create(
                documento=documento, defaults=valores
            )

            if telefones is None and telefone_legado:
                telefones = [{"telefone": telefone_legado, "principal": True}]

            if enderecos is None and (endereco_legado or cidade_legada or uf_legada or cep_legado):
                enderecos = [
                    {
                        "logradouro": endereco_legado or "Endereço não informado",
                        "cidade": cidade_legada,
                        "uf": uf_legada,
                        "cep": cep_legado,
                        "principal": True,
                    }
                ]

            for indice, telefone in enumerate(telefones or []):
                telefone_dados = telefone.copy()
                numero = telefone_dados.pop("telefone")
                telefone_dados.setdefault("principal", indice == 0)
                telefone_dados.setdefault("ativo", True)
                telefone_model.objects.update_or_create(
                    **{nome_parent: pessoa, "telefone": numero},
                    defaults=telefone_dados,
                )

            for indice, endereco in enumerate(enderecos or []):
                endereco_dados = endereco.copy()
                logradouro = endereco_dados.pop("logradouro")
                tipo = endereco_dados.setdefault("tipo", "COMERCIAL")
                endereco_dados.setdefault("principal", indice == 0)
                endereco_dados.setdefault("ativo", True)
                endereco_model.objects.update_or_create(
                    **{nome_parent: pessoa, "tipo": tipo, "logradouro": logradouro},
                    defaults=endereco_dados,
                )

            total += 1
        return total

    def _update_por_chave(self, model, chave, dados):
        total = 0
        for item in dados:
            valores = item.copy()
            valor_chave = valores.pop(chave)
            model.objects.update_or_create(**{chave: valor_chave}, defaults=valores)
            total += 1
        return total
