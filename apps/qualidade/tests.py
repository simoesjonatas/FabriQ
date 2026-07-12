from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.perfis import PRODUCAO, QUALIDADE
from apps.cadastros.models import MateriaPrima
from apps.estoque.models import Lote

from .models import Analise, ResultadoAnalise, StatusAnalise, TipoAnalise

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseQualidade(TestCase):
    def setUp(self):
        self.analista = criar_usuario("analista", perfil=QUALIDADE)
        self.client.login(username="analista", password="senha-forte-123")

        self.mp = MateriaPrima.objects.create(codigo="MP-1", nome="Essência de lavanda")
        self.lote = Lote.objects.create(codigo="LOTE-001", materia_prima=self.mp)
        self.ph = TipoAnalise.objects.create(
            nome="pH",
            unidade="pH",
            valor_minimo=Decimal("5.5"),
            valor_maximo=Decimal("7.0"),
        )
        self.aparencia = TipoAnalise.objects.create(
            nome="Aparência", referencia_texto="Límpido, sem partículas"
        )

    def dados_analise(self, **kwargs):
        dados = {
            "lote": self.lote.pk,
            "observacoes": "",
            "resultados-TOTAL_FORMS": "1",
            "resultados-INITIAL_FORMS": "0",
            "resultados-MIN_NUM_FORMS": "0",
            "resultados-MAX_NUM_FORMS": "1000",
            "resultados-0-tipo": str(self.ph.pk),
            "resultados-0-valor_numerico": "6.2",
            "resultados-0-valor_texto": "",
            "anexos-TOTAL_FORMS": "0",
            "anexos-INITIAL_FORMS": "0",
            "anexos-MIN_NUM_FORMS": "0",
            "anexos-MAX_NUM_FORMS": "1000",
        }
        dados.update(kwargs)
        return dados


class TipoAnaliseTests(BaseQualidade):
    def test_referencia_formatada(self):
        self.assertEqual(self.ph.referencia, "5.5 a 7 pH")
        self.assertEqual(self.aparencia.referencia, "Límpido, sem partículas")

    def test_minimo_maior_que_maximo_e_rejeitado(self):
        response = self.client.post(
            reverse("qualidade:tipo_criar"),
            {
                "nome": "Densidade",
                "unidade": "g/mL",
                "valor_minimo": "2",
                "valor_maximo": "1",
                "referencia_texto": "",
                "ativo": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "maior que o mínimo")
        self.assertFalse(TipoAnalise.objects.filter(nome="Densidade").exists())


class CriarAnaliseTests(BaseQualidade):
    def test_criar_analise_com_resultado(self):
        response = self.client.post(reverse("qualidade:criar"), self.dados_analise())
        analise = Analise.objects.get()
        self.assertRedirects(response, reverse("qualidade:detalhe", args=[analise.pk]))
        self.assertEqual(analise.status, StatusAnalise.EM_ANALISE)
        self.assertEqual(analise.criado_por, self.analista)

        resultado = analise.resultados.get()
        self.assertEqual(resultado.valor_numerico, Decimal("6.2"))
        self.assertFalse(resultado.fora_da_referencia)

    def test_analise_sem_resultado_e_rejeitada(self):
        response = self.client.post(
            reverse("qualidade:criar"),
            self.dados_analise(
                **{"resultados-0-tipo": "", "resultados-0-valor_numerico": ""}
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pelo menos um resultado")
        self.assertEqual(Analise.objects.count(), 0)

    def test_tipo_numerico_exige_valor_numerico(self):
        response = self.client.post(
            reverse("qualidade:criar"),
            self.dados_analise(
                **{
                    "resultados-0-valor_numerico": "",
                    "resultados-0-valor_texto": "ok",
                }
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "informe o valor medido")
        self.assertEqual(Analise.objects.count(), 0)

    def test_tipo_duplicado_e_rejeitado(self):
        dados = self.dados_analise(
            **{
                "resultados-TOTAL_FORMS": "2",
                "resultados-1-tipo": str(self.ph.pk),
                "resultados-1-valor_numerico": "6.5",
                "resultados-1-valor_texto": "",
            }
        )
        response = self.client.post(reverse("qualidade:criar"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "já foi registrado")
        self.assertEqual(Analise.objects.count(), 0)

    def test_preselecao_de_lote_via_querystring(self):
        response = self.client.get(
            reverse("qualidade:criar"), {"lote": self.lote.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{self.lote.pk}" selected')


class ForaDaReferenciaTests(BaseQualidade):
    def test_fora_da_referencia_detectado(self):
        analise = Analise.objects.create(lote=self.lote)
        resultado = ResultadoAnalise.objects.create(
            analise=analise, tipo=self.ph, valor_numerico=Decimal("8.1")
        )
        self.assertTrue(resultado.fora_da_referencia)
        self.assertTrue(analise.tem_resultado_fora_da_referencia)

    def test_qualitativo_nunca_fora_da_referencia(self):
        analise = Analise.objects.create(lote=self.lote)
        resultado = ResultadoAnalise.objects.create(
            analise=analise, tipo=self.aparencia, valor_texto="Límpido"
        )
        self.assertFalse(resultado.fora_da_referencia)


class DecidirTests(BaseQualidade):
    def setUp(self):
        super().setUp()
        self.client.post(reverse("qualidade:criar"), self.dados_analise())
        self.analise = Analise.objects.get()

    def decidir(self, decisao, parecer=""):
        return self.client.post(
            reverse("qualidade:decidir", args=[self.analise.pk]),
            {"decisao": decisao, "parecer": parecer},
        )

    def test_aprovar_registra_responsavel(self):
        self.decidir(StatusAnalise.APROVADA)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.APROVADA)
        self.assertEqual(self.analise.decidido_por, self.analista)
        self.assertIsNotNone(self.analise.decidido_em)

    def test_reprovar_exige_parecer(self):
        self.decidir(StatusAnalise.REPROVADA)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.EM_ANALISE)

        self.decidir(StatusAnalise.REPROVADA, parecer="pH fora da faixa")
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.REPROVADA)
        self.assertEqual(self.analise.parecer, "pH fora da faixa")

    def test_aprovar_sem_resultado_e_bloqueado(self):
        self.analise.resultados.all().delete()
        self.decidir(StatusAnalise.APROVADA)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.EM_ANALISE)

    def test_analise_decidida_trava_edicao_e_nova_decisao(self):
        self.decidir(StatusAnalise.APROVADA)

        response = self.client.get(reverse("qualidade:editar", args=[self.analise.pk]))
        self.assertRedirects(
            response, reverse("qualidade:detalhe", args=[self.analise.pk])
        )

        self.decidir(StatusAnalise.REPROVADA, parecer="mudei de ideia")
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.APROVADA)


class PermissoesTests(TestCase):
    def setUp(self):
        criar_usuario("analista", perfil=QUALIDADE)
        criar_usuario("operador", perfil=PRODUCAO)

    def test_producao_nao_acessa_qualidade(self):
        self.client.login(username="operador", password="senha-forte-123")
        for rota in ["qualidade:lista", "qualidade:criar", "qualidade:tipo_lista"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_qualidade_acessa_tudo(self):
        self.client.login(username="analista", password="senha-forte-123")
        for rota in ["qualidade:lista", "qualidade:criar", "qualidade:tipo_lista"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)
