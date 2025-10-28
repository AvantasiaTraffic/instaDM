from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_dm(name: str, lang: str = "english", custom_template_es: str = None, custom_template_en: str = None):
    is_spanish = lang.lower().startswith("es")

    if is_spanish and custom_template_es:
        prompt = custom_template_es.replace("{name}", name)
    elif not is_spanish and custom_template_en:
        prompt = custom_template_en.replace("{name}", name)
    else:
        # fallback a plantilla base
        if is_spanish:
            prompt = f"""Eres una autora amable que quiere conectar con nuevos lectores.
Genera un mensaje breve (máx. 250 caracteres) dirigido a {name},
invitándole a leer los primeros capítulos gratis de un thriller powermetal titulado 'Sinfonía de la Oscuridad'.
Incluye el enlace: https://www.amazon.es/dp/B0DV5NZ9RX."""
        else:
            prompt = f"""You are a friendly author who wants to connect with new readers.
Write a short message (max 250 characters) addressed to {name},
inviting them to read the first free chapters of a powermetal thriller titled 'Darkness Symphony'.
Include the link: https://www.amazon.com/dp/B0DYSNXD4B."""

    resp = client.responses.create(model="gpt-4o-mini", input=prompt)
    return resp.output_text.strip()
