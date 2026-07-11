from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.perfis import ADMINISTRADOR, PRODUCAO

User = get_user_model()


class HomePageTests(TestCase):
    def test_anonimo_e_redirecionado_para_login(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_logado_ve_a_home(self):
        User.objects.create_user(username="maria", password="senha-forte-123")
        self.client.login(username="maria", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_administrador_ve_o_modulo_usuarios(self):
        usuario = User.objects.create_user(username="admin", password="senha-forte-123")
        usuario.groups.add(Group.objects.get(name=ADMINISTRADOR))
        self.client.login(username="admin", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Usuários")

    def test_producao_nao_ve_o_modulo_usuarios(self):
        usuario = User.objects.create_user(username="operador", password="senha-forte-123")
        usuario.groups.add(Group.objects.get(name=PRODUCAO))
        self.client.login(username="operador", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Usuários")
        self.assertContains(response, "Nenhum módulo disponível para o seu perfil")
