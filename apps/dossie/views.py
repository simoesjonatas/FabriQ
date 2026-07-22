import logging

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from apps.accounts.mixins import AcessoQualquerModuloMixin
from apps.estoque.models import Lote

from .models import GeracaoDossie, hash_do_pdf, proxima_versao
from .servicos import montar_dossie

logger = logging.getLogger("fabriq")

MODULOS = (
    "qualidade", "producao", "ordens", "estoque", "cadastros", "expedicao",
)


def _lote_de_produto(pk):
    return get_object_or_404(
        Lote.objects.select_related("produto"), pk=pk, produto__isnull=False
    )


class DossieView(AcessoQualquerModuloMixin, View):
    """Dossiê do lote na tela (Etapa 12)."""

    modulos = MODULOS

    def get(self, request, pk):
        lote = _lote_de_produto(pk)
        from django.shortcuts import render

        return render(
            request,
            "dossie/dossie.html",
            {
                "dossie": montar_dossie(lote),
                "lote": lote,
                "geracoes": lote.dossies.select_related("gerado_por")[:10],
            },
        )


class DossiePDFView(AcessoQualquerModuloMixin, View):
    """
    Gera o PDF do dossiê e **registra a geração** (quem, quando, versão,
    hash). O PDF reflete o banco no instante da geração.
    """

    modulos = MODULOS

    def post(self, request, pk):
        from weasyprint import HTML

        lote = _lote_de_produto(pk)
        agora = timezone.localtime()
        versao = proxima_versao(lote)

        html = render_to_string(
            "dossie/dossie_pdf.html",
            {
                "dossie": montar_dossie(lote),
                "lote": lote,
                "gerado_em": agora,
                "gerado_por": request.user,
                "versao": versao,
                "codigo": f"DOS-{lote.pk:05d}-{versao:02d}",
                "origem": request.build_absolute_uri(),
            },
            request=request,
        )
        pdf = HTML(
            string=html, base_url=request.build_absolute_uri("/")
        ).write_pdf()

        geracao = GeracaoDossie(
            lote=lote,
            versao=versao,
            gerado_por=request.user,
            hash_arquivo=hash_do_pdf(pdf),
        )
        geracao.arquivo.save(
            f"dossie-{lote.codigo}-v{versao:02d}.pdf",
            ContentFile(pdf),
            save=False,
        )
        geracao.save()

        logger.info(
            "Dossiê %s do lote %s gerado por %s",
            geracao.codigo, lote.codigo, request.user,
        )

        resposta = HttpResponse(pdf, content_type="application/pdf")
        resposta["Content-Disposition"] = (
            f'attachment; filename="dossie-{lote.codigo}-v{versao:02d}.pdf"'
        )
        return resposta

    def get(self, request, pk):
        messages.info(
            request, "Use o botão “Gerar PDF” para emitir uma nova versão do dossiê."
        )
        return redirect("dossie:detalhe", pk=pk)
