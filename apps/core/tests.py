from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_pagina_inicial_carrega(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FabriQ")

    def test_pagina_inicial_usa_template_base(self):
        response = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "core/home.html")
