from openai import OpenAI
import os
from dotenv import load_dotenv

# Cargar variables del .env antes de crear el cliente
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_dm(name: str, lang: str = "english"):
    if lang.lower().startswith("es"):
        title = "Sinfonía de la Oscuridad"
        link = "https://www.amazon.es/dp/B0DV5NZ9RX"
        prompt = f"""
Eres una autora amable que quiere conectar con nuevos lectores.
Genera un mensaje breve (máx. 250 caracteres) dirigido a {name},
invitándole a leer los primeros capítulos gratis de un thriller powermetal titulado '{title}'.
Incluye el enlace: {link}.
Usa un tono cercano, natural y en español.
"""
    else:
        title = "Darkness Symphony"
        link = "https://www.amazon.com/dp/B0DYSNXD4B"
        prompt = f"""
You are a friendly author who wants to connect with new readers.
Write a short message (max 250 characters) addressed to {name},
inviting them to read the first free chapters of a powermetal thriller titled '{title}'.
Include the link: {link}.
Use a warm, natural tone in English.
"""

    resp = client.responses.create(model="gpt-4o-mini", input=prompt)
    return resp.output_text.strip()
