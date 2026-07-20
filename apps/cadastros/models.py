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


class StatusEquipamento(models.TextChoices):
    LIBERADO = "LIBERADO", "Liberado"
    MANUTENCAO = "MANUTENCAO", "Em manutenção"
    INTERDITADO = "INTERDITADO", "Interditado"


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
    status = models.CharField(
        "situação",
        max_length=15,
        choices=StatusEquipamento.choices,
        default=StatusEquipamento.LIBERADO,
    )
    ultima_limpeza = models.DateField("última limpeza", null=True, blank=True)
    ultima_sanitizacao = models.DateField("última sanitização", null=True, blank=True)
    manutencao_validade = models.DateField(
        "validade da manutenção", null=True, blank=True
    )
    calibracao_validade = models.DateField(
        "validade da calibração", null=True, blank=True
    )
    localizacao = models.CharField("localização", max_length=100, blank=True)
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

    @property
    def badge_status(self) -> str:
        return {
            StatusEquipamento.LIBERADO: "text-bg-success",
            StatusEquipamento.MANUTENCAO: "text-bg-warning",
            StatusEquipamento.INTERDITADO: "text-bg-danger",
        }.get(self.status, "text-bg-secondary")

    def motivo_impedimento_uso(self) -> str:
        """
        Motivo pelo qual o equipamento NÃO pode ser usado na OP, ou ""
        se está apto (Etapa 6c). Mensagem pronta para a tela.
        """
        from django.utils import timezone

        if self.status == StatusEquipamento.MANUTENCAO:
            return f"{self.codigo} está em manutenção"
        if self.status == StatusEquipamento.INTERDITADO:
            return f"{self.codigo} está interditado"
        if self.ultima_limpeza is None:
            return f"{self.codigo} sem limpeza registrada"
        hoje = timezone.localdate()
        if self.calibracao_validade and self.calibracao_validade < hoje:
            return (
                f"{self.codigo} com calibração vencida em "
                f"{self.calibracao_validade:%d/%m/%Y}"
            )
        if self.manutencao_validade and self.manutencao_validade < hoje:
            return (
                f"{self.codigo} com manutenção vencida em "
                f"{self.manutencao_validade:%d/%m/%Y}"
            )
        return ""

    def pode_ser_usado(self) -> bool:
        return self.motivo_impedimento_uso() == ""


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
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        abstract = True
        ordering = ["razao_social"]

    def __str__(self) -> str:
        return self.nome_fantasia or self.razao_social

    @property
    def documento_formatado(self) -> str:
        if len(self.documento) == 11:
            return (
                f"{self.documento[:3]}.{self.documento[3:6]}."
                f"{self.documento[6:9]}-{self.documento[9:]}"
            )
        if len(self.documento) == 14:
            return (
                f"{self.documento[:2]}.{self.documento[2:5]}."
                f"{self.documento[5:8]}/{self.documento[8:12]}-"
                f"{self.documento[12:]}"
            )
        return self.documento

    @property
    def telefone_principal(self) -> str:
        if not self.pk:
            return ""
        telefone = self.telefones.filter(ativo=True).order_by("-principal", "id").first()
        return telefone.telefone if telefone else ""

    @property
    def endereco_principal(self):
        if not self.pk:
            return None
        return self.enderecos.filter(ativo=True).order_by("-principal", "id").first()

    @property
    def cidade_uf_principal(self) -> str:
        endereco = self.endereco_principal
        if not endereco:
            return ""
        if endereco.cidade and endereco.uf:
            return f"{endereco.cidade}/{endereco.uf}"
        return endereco.cidade or endereco.uf


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


class TipoTelefone(models.TextChoices):
    CELULAR = "CELULAR", "Celular"
    COMERCIAL = "COMERCIAL", "Comercial"
    FINANCEIRO = "FINANCEIRO", "Financeiro"
    RESIDENCIAL = "RESIDENCIAL", "Residencial"
    OUTRO = "OUTRO", "Outro"


class TipoEndereco(models.TextChoices):
    COMERCIAL = "COMERCIAL", "Comercial"
    ENTREGA = "ENTREGA", "Entrega"
    COBRANCA = "COBRANCA", "Cobrança"
    RESIDENCIAL = "RESIDENCIAL", "Residencial"
    OUTRO = "OUTRO", "Outro"


class TelefoneBase(ModeloBase):
    tipo = models.CharField(
        "tipo", max_length=20, choices=TipoTelefone.choices, default=TipoTelefone.COMERCIAL
    )
    telefone = models.CharField("telefone", max_length=20)
    contato = models.CharField("contato", max_length=100, blank=True)
    principal = models.BooleanField("principal", default=False)
    observacoes = models.CharField("observações", max_length=150, blank=True)

    class Meta:
        abstract = True
        ordering = ["-principal", "tipo", "telefone"]

    def __str__(self) -> str:
        if self.contato:
            return f"{self.telefone} · {self.contato}"
        return self.telefone


class EnderecoBase(ModeloBase):
    tipo = models.CharField(
        "tipo", max_length=20, choices=TipoEndereco.choices, default=TipoEndereco.COMERCIAL
    )
    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField("logradouro", max_length=150)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField("complemento", max_length=80, blank=True)
    bairro = models.CharField("bairro", max_length=100, blank=True)
    cidade = models.CharField("cidade", max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    principal = models.BooleanField("principal", default=False)
    observacoes = models.CharField("observações", max_length=150, blank=True)

    class Meta:
        abstract = True
        ordering = ["-principal", "tipo", "logradouro"]

    def __str__(self) -> str:
        return self.resumo

    @property
    def resumo(self) -> str:
        primeira_linha = self.logradouro
        if self.numero:
            primeira_linha = f"{primeira_linha}, {self.numero}"
        if self.complemento:
            primeira_linha = f"{primeira_linha} · {self.complemento}"

        localidade = ""
        if self.cidade and self.uf:
            localidade = f"{self.cidade}/{self.uf}"
        else:
            localidade = self.cidade or self.uf

        return " · ".join(parte for parte in [primeira_linha, localidade] if parte)


class ClienteTelefone(TelefoneBase):
    cliente = models.ForeignKey(
        Cliente,
        verbose_name="cliente",
        on_delete=models.CASCADE,
        related_name="telefones",
    )

    class Meta(TelefoneBase.Meta):
        verbose_name = "telefone do cliente"
        verbose_name_plural = "telefones do cliente"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente"],
                condition=models.Q(principal=True, ativo=True),
                name="cliente_telefone_principal_unico",
                violation_error_message="Marque apenas um telefone principal.",
            ),
        ]


class FornecedorTelefone(TelefoneBase):
    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name="fornecedor",
        on_delete=models.CASCADE,
        related_name="telefones",
    )

    class Meta(TelefoneBase.Meta):
        verbose_name = "telefone do fornecedor"
        verbose_name_plural = "telefones do fornecedor"
        constraints = [
            models.UniqueConstraint(
                fields=["fornecedor"],
                condition=models.Q(principal=True, ativo=True),
                name="fornecedor_telefone_principal_unico",
                violation_error_message="Marque apenas um telefone principal.",
            ),
        ]


class ClienteEndereco(EnderecoBase):
    cliente = models.ForeignKey(
        Cliente,
        verbose_name="cliente",
        on_delete=models.CASCADE,
        related_name="enderecos",
    )

    class Meta(EnderecoBase.Meta):
        verbose_name = "endereço do cliente"
        verbose_name_plural = "endereços do cliente"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente"],
                condition=models.Q(principal=True, ativo=True),
                name="cliente_endereco_principal_unico",
                violation_error_message="Marque apenas um endereço principal.",
            ),
        ]


class FornecedorEndereco(EnderecoBase):
    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name="fornecedor",
        on_delete=models.CASCADE,
        related_name="enderecos",
    )

    class Meta(EnderecoBase.Meta):
        verbose_name = "endereço do fornecedor"
        verbose_name_plural = "endereços do fornecedor"
        constraints = [
            models.UniqueConstraint(
                fields=["fornecedor"],
                condition=models.Q(principal=True, ativo=True),
                name="fornecedor_endereco_principal_unico",
                violation_error_message="Marque apenas um endereço principal.",
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
    critico = models.BooleanField(
        "material crítico",
        default=False,
        help_text="Exige dupla conferência na pesagem (conferente ≠ operador).",
    )

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


class Balanca(ModeloBase):
    """
    Balança usada na pesagem dos materiais (Etapa 6b). Uma balança com
    calibração vencida não pode ser usada na produção.
    """

    codigo = models.CharField("código", max_length=30, unique=True)
    descricao = models.CharField("descrição", max_length=120)
    capacidade = models.DecimalField(
        "capacidade",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Capacidade máxima, na unidade de pesagem.",
    )
    unidade_capacidade = models.CharField(
        "unidade da capacidade", max_length=20, blank=True, help_text="Ex.: kg, g."
    )
    calibracao_validade = models.DateField(
        "validade da calibração", null=True, blank=True
    )
    localizacao = models.CharField("localização", max_length=100, blank=True)

    class Meta:
        verbose_name = "balança"
        verbose_name_plural = "balanças"
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.descricao}"

    @property
    def calibracao_vencida(self) -> bool:
        from django.utils import timezone

        return (
            self.calibracao_validade is not None
            and self.calibracao_validade < timezone.localdate()
        )
