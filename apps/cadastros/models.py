"""
Cadastros gerais do FabriQ (Fase 2).

Todos herdam ModeloBase: auditoria (criado/atualizado por/em) e o campo
`ativo` para inativação — registros nunca são excluídos definitivamente.
"""

from django.db import models

from apps.core.models import ModeloBase

UF_CHOICES = [
    ("AC", "AC"), ("AL", "AL"), ("AP", "AP"), ("AM", "AM"), ("BA", "BA"),
    ("CE", "CE"), ("DF", "DF"), ("ES", "ES"), ("GO", "GO"), ("MA", "MA"),
    ("MT", "MT"), ("MS", "MS"), ("MG", "MG"), ("PA", "PA"), ("PB", "PB"),
    ("PR", "PR"), ("PE", "PE"), ("PI", "PI"), ("RJ", "RJ"), ("RN", "RN"),
    ("RS", "RS"), ("RO", "RO"), ("RR", "RR"), ("SC", "SC"), ("SP", "SP"),
    ("SE", "SE"), ("TO", "TO"),
]


class Unidade(models.TextChoices):
    UNIDADE = "UN", "Unidade"
    CAIXA = "CX", "Caixa"
    QUILOGRAMA = "KG", "Quilograma"
    GRAMA = "G", "Grama"
    LITRO = "L", "Litro"
    MILILITRO = "ML", "Mililitro"


class Setor(ModeloBase):
    nome = models.CharField("nome", max_length=100, unique=True)
    descricao = models.TextField("descrição", blank=True)

    class Meta:
        verbose_name = "setor"
        verbose_name_plural = "setores"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Equipamento(ModeloBase):
    codigo = models.CharField("código", max_length=30, unique=True)
    nome = models.CharField("nome", max_length=100)
    setor = models.ForeignKey(
        Setor,
        verbose_name="setor",
        on_delete=models.PROTECT,
        related_name="equipamentos",
        null=True,
        blank=True,
    )
    capacidade = models.DecimalField(
        "capacidade",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Capacidade por lote ou por hora, conforme a unidade informada.",
    )
    unidade_capacidade = models.CharField(
        "unidade da capacidade",
        max_length=20,
        blank=True,
        help_text="Ex.: kg/lote, L/h, un/h.",
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "equipamento"
        verbose_name_plural = "equipamentos"
        ordering = ["nome"]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.nome}"


class PessoaBase(ModeloBase):
    """Campos comuns de clientes e fornecedores."""

    razao_social = models.CharField("razão social / nome", max_length=150)
    nome_fantasia = models.CharField("nome fantasia", max_length=150, blank=True)
    documento = models.CharField(
        "CNPJ/CPF",
        max_length=18,
        blank=True,
        help_text="Somente números ou com máscara; usado em notas e relatórios.",
    )
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    endereco = models.CharField("endereço", max_length=200, blank=True)
    cidade = models.CharField("cidade", max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        abstract = True
        ordering = ["razao_social"]

    def __str__(self) -> str:
        return self.nome_fantasia or self.razao_social


class Cliente(PessoaBase):
    class Meta(PessoaBase.Meta):
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        constraints = [
            models.UniqueConstraint(
                fields=["documento"],
                condition=~models.Q(documento=""),
                name="cliente_documento_unico",
                violation_error_message="Já existe um cliente com este CNPJ/CPF.",
            ),
        ]


class Fornecedor(PessoaBase):
    class Meta(PessoaBase.Meta):
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        constraints = [
            models.UniqueConstraint(
                fields=["documento"],
                condition=~models.Q(documento=""),
                name="fornecedor_documento_unico",
                violation_error_message="Já existe um fornecedor com este CNPJ/CPF.",
            ),
        ]


class ItemBase(ModeloBase):
    """Campos comuns dos itens de estoque (produto, MP, embalagem)."""

    codigo = models.CharField("código", max_length=30, unique=True)
    nome = models.CharField("nome", max_length=150)
    unidade = models.CharField(
        "unidade", max_length=2, choices=Unidade.choices, default=Unidade.UNIDADE
    )
    estoque_minimo = models.DecimalField(
        "estoque mínimo",
        max_digits=12,
        decimal_places=3,
        default=0,
        help_text="Abaixo desta quantidade o item aparece como estoque crítico.",
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        abstract = True
        ordering = ["nome"]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.nome}"


class Produto(ItemBase):
    descricao = models.TextField("descrição", blank=True)

    class Meta(ItemBase.Meta):
        verbose_name = "produto"
        verbose_name_plural = "produtos"


class MateriaPrima(ItemBase):
    class Meta(ItemBase.Meta):
        verbose_name = "matéria-prima"
        verbose_name_plural = "matérias-primas"


class TipoEmbalagem(models.TextChoices):
    FRASCO = "FRASCO", "Frasco"
    TAMPA = "TAMPA", "Tampa"
    VALVULA = "VALVULA", "Válvula"
    ROTULO = "ROTULO", "Rótulo"
    CAIXA = "CAIXA", "Caixa"
    OUTRO = "OUTRO", "Outro"


class Embalagem(ItemBase):
    tipo = models.CharField(
        "tipo", max_length=10, choices=TipoEmbalagem.choices, default=TipoEmbalagem.OUTRO
    )

    class Meta(ItemBase.Meta):
        verbose_name = "embalagem"
        verbose_name_plural = "embalagens"
