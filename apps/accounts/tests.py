from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def test_str_usa_nome_completo(self):
        user = User.objects.create_user(
            username="maria", first_name="Maria", last_name="Silva"
        )
        self.assertEqual(str(user), "Maria Silva")

    def test_str_usa_username_quando_nao_ha_nome(self):
        user = User.objects.create_user(username="joao")
        self.assertEqual(str(user), "joao")

    def test_modelo_de_usuario_customizado_esta_ativo(self):
        self.assertEqual(User._meta.label, "accounts.User")
