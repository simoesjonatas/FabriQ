import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .perfis import ADMINISTRADOR, PERFIS, PRODUCAO, usuario_acessa_modulo

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123", **kwargs):
    usuario = User.objects.create_user(username=username, password=senha, **kwargs)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class UserModelTests(TestCase):
    def test_str_usa_nome_completo(self):
        usuario = User.objects.create_user(
            username="maria", first_name="Maria", last_name="Silva"
        )
        self.assertEqual(str(usuario), "Maria Silva")

    def test_str_usa_username_quando_nao_ha_nome(self):
        usuario = User.objects.create_user(username="joao")
        self.assertEqual(str(usuario), "joao")

    def test_modelo_de_usuario_customizado_esta_ativo(self):
        self.assertEqual(User._meta.label, "accounts.User")


class PerfisTests(TestCase):
    def test_migracao_criou_os_oito_perfis(self):
        nomes = set(Group.objects.values_list("name", flat=True))
        self.assertEqual(nomes, set(PERFIS))
        self.assertEqual(len(PERFIS), 8)

    def test_administrador_acessa_modulo_usuarios(self):
        admin = criar_usuario("admin1", perfil=ADMINISTRADOR)
        self.assertTrue(usuario_acessa_modulo(admin, "usuarios"))

    def test_superusuario_acessa_modulo_usuarios(self):
        superusuario = User.objects.create_superuser(username="root", password="x")
        self.assertTrue(usuario_acessa_modulo(superusuario, "usuarios"))

    def test_outros_perfis_nao_acessam_modulo_usuarios(self):
        producao = criar_usuario("operador", perfil=PRODUCAO)
        self.assertFalse(usuario_acessa_modulo(producao, "usuarios"))

    def test_usuario_inativo_nao_acessa_nada(self):
        admin = criar_usuario("admin2", perfil=ADMINISTRADOR, is_active=False)
        self.assertFalse(usuario_acessa_modulo(admin, "usuarios"))

    def test_modulo_inexistente_nega_ate_para_superusuario(self):
        superusuario = User.objects.create_superuser(username="root2", password="x")
        self.assertFalse(usuario_acessa_modulo(superusuario, "modulo-com-typo"))


class LoginTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("maria", perfil=PRODUCAO)

    def test_pagina_de_login_carrega(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acesse sua conta")

    def test_login_valido_redireciona_para_home(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "maria", "password": "senha-forte-123"},
        )
        self.assertRedirects(response, reverse("core:home"))

    def test_login_invalido_mostra_erro(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "maria", "password": "senha-errada"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-danger")

    def test_usuario_inativo_nao_entra(self):
        self.usuario.is_active = False
        self.usuario.save()
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "maria", "password": "senha-forte-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-danger")

    def test_login_registra_ultimo_acesso(self):
        self.assertIsNone(self.usuario.last_login)
        self.client.post(
            reverse("accounts:login"),
            {"username": "maria", "password": "senha-forte-123"},
        )
        self.usuario.refresh_from_db()
        self.assertIsNotNone(self.usuario.last_login)

    def test_logout_redireciona_para_login(self):
        self.client.login(username="maria", password="senha-forte-123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))


class RecuperarSenhaTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("maria", email="maria@exemplo.com")

    def test_fluxo_completo_de_recuperacao(self):
        # Solicita o link
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "maria@exemplo.com"}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("maria", mail.outbox[0].body)

        # Extrai o link do e-mail e abre (redireciona para a URL com token em sessão)
        link = re.search(r"http://[^\s]+", mail.outbox[0].body).group()
        response = self.client.get(link, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Definir nova senha")

        # Define a nova senha
        url_formulario = response.request["PATH_INFO"]
        response = self.client.post(
            url_formulario,
            {"new_password1": "NovaSenha!2026", "new_password2": "NovaSenha!2026"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))

        # Consegue entrar com a senha nova
        self.assertTrue(self.client.login(username="maria", password="NovaSenha!2026"))

    def test_email_desconhecido_nao_envia_mas_nao_revela(self):
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "nao-existe@exemplo.com"}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


class UsuarioCrudTests(TestCase):
    def setUp(self):
        self.admin = criar_usuario("admin", perfil=ADMINISTRADOR)
        self.operador = criar_usuario("operador", perfil=PRODUCAO)

    def entrar_como_admin(self):
        self.client.login(username="admin", password="senha-forte-123")

    def test_anonimo_e_redirecionado_para_login(self):
        response = self.client.get(reverse("accounts:usuario_lista"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_perfil_sem_acesso_recebe_403(self):
        self.client.login(username="operador", password="senha-forte-123")
        response = self.client.get(reverse("accounts:usuario_lista"))
        self.assertEqual(response.status_code, 403)

    def test_administrador_ve_a_lista(self):
        self.entrar_como_admin()
        response = self.client.get(reverse("accounts:usuario_lista"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "operador")

    def test_pesquisa_filtra_usuarios(self):
        self.entrar_como_admin()
        response = self.client.get(reverse("accounts:usuario_lista"), {"q": "operador"})
        self.assertContains(response, "operador")
        self.assertNotContains(response, ">admin<")

    def test_filtro_de_inativos(self):
        criar_usuario("desligado", is_active=False)
        self.entrar_como_admin()
        response = self.client.get(
            reverse("accounts:usuario_lista"), {"status": "inativos"}
        )
        self.assertContains(response, "desligado")
        self.assertNotContains(response, "operador")

    def test_cadastrar_usuario_com_perfil(self):
        self.entrar_como_admin()
        grupo_pcp = Group.objects.get(name="PCP")
        response = self.client.post(
            reverse("accounts:usuario_criar"),
            {
                "username": "novo.usuario",
                "first_name": "Novo",
                "last_name": "Usuário",
                "email": "novo@exemplo.com",
                "password1": "SenhaInicial!2026",
                "password2": "SenhaInicial!2026",
                "perfis": [grupo_pcp.pk],
            },
        )
        self.assertRedirects(response, reverse("accounts:usuario_lista"))
        novo = User.objects.get(username="novo.usuario")
        self.assertEqual(list(novo.groups.all()), [grupo_pcp])

    def test_inativar_usuario_em_vez_de_excluir(self):
        self.entrar_como_admin()
        response = self.client.post(
            reverse("accounts:usuario_editar", args=[self.operador.pk]),
            {
                "first_name": "Operador",
                "last_name": "",
                "email": "",
                "perfis": [],
                # is_active desmarcado = ausente do POST
            },
        )
        self.assertRedirects(response, reverse("accounts:usuario_lista"))
        self.operador.refresh_from_db()
        self.assertFalse(self.operador.is_active)
        # O registro continua existindo (nunca excluímos)
        self.assertTrue(User.objects.filter(pk=self.operador.pk).exists())

    def test_nao_pode_inativar_o_proprio_usuario(self):
        self.entrar_como_admin()
        response = self.client.post(
            reverse("accounts:usuario_editar", args=[self.admin.pk]),
            {"first_name": "", "last_name": "", "email": "", "perfis": []},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "não pode inativar o seu próprio usuário")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
