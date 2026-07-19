"""
Serviços da trilha de auditoria.

`registrar_alteracoes` compara duas versões do mesmo registro campo a
campo e cria um `RegistroAuditoria` por campo alterado, com valor
anterior, valor novo, usuário e justificativa. A integração automática
fica em `ModeloAuditado.save()` (apps/core/models.py): qualquer tela ou
fluxo que salve um modelo auditado alimenta a trilha sem código extra.

`registrar_evento` registra ações com significado próprio (aprovação,
liberação, cancelamento, exceção de bloqueio) — usado pelos fluxos de
decisão, além das alterações campo a campo.
"""

import datetime

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import formats
from django.utils import timezone as fuso

from apps.core import formatos

from .models import AcaoAuditoria, RegistroAuditoria

# Campos de controle que não entram na comparação: os de auditoria
# básica mudam em todo save (e o usuário já fica no próprio registro
# da trilha); senha e último acesso nunca devem aparecer em tela.
CAMPOS_NAO_AUDITADOS = {
    "criado_em",
    "atualizado_em",
    "criado_por",
    "atualizado_por",
    "password",
    "last_login",
}


def _campos_auditaveis(instancia):
    for campo in instancia._meta.concrete_fields:
        if campo.primary_key or campo.name in CAMPOS_NAO_AUDITADOS:
            continue
        yield campo


def _valor_bruto(instancia, campo):
    """Valor para comparação: FK pelo id, arquivo pelo nome."""
    valor = getattr(instancia, campo.attname)
    if isinstance(campo, models.FileField) and valor is not None:
        return valor.name
    return valor


def valor_legivel(instancia, campo) -> str:
    """Valor de um campo como o usuário o vê na tela."""
    valor = getattr(instancia, campo.attname)
    if valor in (None, ""):
        return ""
    if campo.choices:
        return str(getattr(instancia, f"get_{campo.name}_display")())
    if campo.is_relation:
        relacionado = getattr(instancia, campo.name)
        return str(relacionado) if relacionado is not None else ""
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(campo, models.DecimalField):
        return formatos.quantidade(valor)
    if isinstance(campo, models.FileField):
        return valor.name
    if isinstance(valor, datetime.datetime):
        return formats.date_format(fuso.localtime(valor), "SHORT_DATETIME_FORMAT")
    if isinstance(valor, datetime.date):
        return formats.date_format(valor, "SHORT_DATE_FORMAT")
    return str(valor)


def _criar_registro(instancia, acao, usuario, justificativa="", **valores):
    return RegistroAuditoria.objects.create(
        content_type=ContentType.objects.get_for_model(type(instancia)),
        object_id=instancia.pk,
        objeto_repr=str(instancia)[:200],
        acao=acao,
        usuario=usuario,
        justificativa=justificativa.strip(),
        **valores,
    )


def registrar_criacao(instancia, usuario, justificativa=""):
    """Um registro único de criação (os valores estão no próprio objeto)."""
    return _criar_registro(instancia, AcaoAuditoria.CRIACAO, usuario, justificativa)


def registrar_alteracoes(instancia_antiga, instancia_nova, usuario, justificativa=""):
    """
    Compara campo a campo e cria um RegistroAuditoria por campo alterado.
    Inativar (ativo True -> False) é registrado com a ação própria.
    Retorna a lista de registros criados.
    """
    registros = []
    for campo in _campos_auditaveis(instancia_nova):
        anterior = _valor_bruto(instancia_antiga, campo)
        novo = _valor_bruto(instancia_nova, campo)
        if anterior == novo:
            continue

        acao = AcaoAuditoria.ALTERACAO
        if campo.name == "ativo" and anterior and not novo:
            acao = AcaoAuditoria.INATIVACAO

        registros.append(
            _criar_registro(
                instancia_nova,
                acao,
                usuario,
                justificativa,
                campo=str(campo.verbose_name),
                valor_anterior=valor_legivel(instancia_antiga, campo),
                valor_novo=valor_legivel(instancia_nova, campo),
            )
        )
    return registros


def registrar_evento(
    instancia,
    acao,
    usuario,
    justificativa="",
    campo="",
    valor_anterior="",
    valor_novo="",
):
    """Registra uma ação com significado próprio (aprovação, liberação...)."""
    return _criar_registro(
        instancia,
        acao,
        usuario,
        justificativa,
        campo=campo,
        valor_anterior=valor_anterior,
        valor_novo=valor_novo,
    )


def trilha_de(instancia):
    """Todos os registros de auditoria de um objeto, do mais recente ao mais antigo."""
    return RegistroAuditoria.objects.filter(
        content_type=ContentType.objects.get_for_model(type(instancia)),
        object_id=instancia.pk,
    ).select_related("usuario")
