import streamlit as st
import pandas as pd
import os
import time
import random
import sqlite3
from dotenv import load_dotenv
from instagrapi.exceptions import ClientError, RateLimitError
from insta import login, extract_media_pk, get_likers, ensure_login
from db import init_db, save_likers, get_pending, mark_contacted, db, get_post_progress, save_post_progress, get_ai_templates, save_ai_templates
from ai import generate_dm

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="🤖 InstaDM", page_icon="💬", layout="wide")
st.title("🤖 InstaDM")
st.info(
    "ℹ️ Los mensajes a cuentas privadas no se envían. Solo se procesan cuentas públicas contactables.\n\n"
    "🔒 Al conectarte desde esta herramienta, Instagram puede cerrar tu sesión en la app oficial "
    "o pedir que confirmes tu identidad. Esto ocurre porque detecta un nuevo inicio de sesión desde otro dispositivo. "
    "No te preocupes: es totalmente seguro y basta con confirmar que fuiste tú.\n\n"
    "⚙️ **Recomendaciones para mantener tu cuenta segura:**\n\n"
    "• Espera entre **3 y 6 segundos** entre acciones (ya automatizado por la aplicación).\n\n"
    "• No realices más de **100 interacciones (likes o mensajes)** por hora.\n\n"
    "• Deja pasar **10–15 minutos entre lotes grandes** para evitar sobrecarga o bloqueos temporales.\n\n"
    "• Si aparece una alerta o la sesión se cierra, simplemente **entra en tu app oficial**, confirma que fuiste tú y regresa aquí.\n\n"
    "⏳ Estos tiempos y pausas están pensados para que tu actividad parezca natural ante Instagram "
    "y evitar que tu cuenta sea marcada por uso automatizado."
)

load_dotenv()
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")

if not IG_USERNAME or not IG_PASSWORD:
    st.error("⚠️ Debes definir IG_USERNAME e IG_PASSWORD en tu archivo .env")
    st.stop()

# Inicializar base de datos
init_db()

# --- SESIÓN PERSISTENTE ---
if "cl" not in st.session_state:
    st.session_state["cl"] = None
if "likers_data" not in st.session_state:
    st.session_state["likers_data"] = []
if "offset" not in st.session_state:
    st.session_state["offset"] = 0

# --- SIDEBAR IZQUIERDA ---
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {width: 420px !important;}
    </style>
    """,
    unsafe_allow_html=True
)

with st.sidebar:
    st.header("⚙️ Configuración InstaDM")
    num_likes = st.number_input("Número de likes por lote:", min_value=1, max_value=100, value=10, step=1)
    num_messages = st.number_input("Número máximo de mensajes a enviar:", min_value=1, max_value=100, value=10, step=1)

    # --- NUEVO CAMPO DE PLANTILLA PERSONALIZADA ---
    st.subheader("🧠 Plantilla de mensaje IA")
    stored_es, stored_en = get_ai_templates()

    default_es = """Eres una autora amable que quiere conectar con nuevos lectores.
    Genera un mensaje breve (máx. 250 caracteres) dirigido a {name},
    invitándole a leer los primeros capítulos gratis de un thriller powermetal titulado 'Sinfonía de la Oscuridad'.
    Incluye el enlace: https://www.amazon.es/dp/B0DV5NZ9RX.
    Usa un tono cercano y natural en español.
    """

    default_en = """You are a friendly author who wants to connect with new readers.
    Write a short message (max 250 characters) addressed to {name},
    inviting them to read the first free chapters of a powermetal thriller titled 'Darkness Symphony'.
    Include the link: https://www.amazon.com/dp/B0DYSNXD4B.
    Use a warm, natural tone in English.
    """

    col1, col2 = st.columns(2)

    with col1:
        custom_es = st.text_area("🇪🇸 Plantilla en español:", value=stored_es or default_es, height=180)
    with col2:
        custom_en = st.text_area("🇺🇸 Template in English:", value=stored_en or default_en, height=180)

    if (custom_es != stored_es) or (custom_en != stored_en):
        save_ai_templates(custom_es, custom_en)
        st.success("💾 Plantillas actualizadas y guardadas en base de datos.")

    # Guardar en sesión
    st.session_state["custom_template_es"] = custom_es
    st.session_state["custom_template_en"] = custom_en

    st.divider()
    st.subheader("👁️ Visualización de datos")

    if st.button("📋 Ver todos los usuarios"):
        conn = db()
        df_all = pd.read_sql_query(
            "SELECT username, full_name, is_private, contacted, language FROM contacts ORDER BY id DESC",
            conn
        )
        conn.close()
        st.write(f"**Total:** {len(df_all)} usuarios en base de datos")
        st.dataframe(df_all, width="stretch")

    if st.button("🕓 Ver pendientes"):
        conn = db()
        df_pending = pd.read_sql_query(
            "SELECT username, full_name, language FROM contacts WHERE contacted=0 AND is_private=0",
            conn
        )
        conn.close()
        st.write(f"**Pendientes:** {len(df_pending)} usuarios por contactar")
        st.dataframe(df_pending, width="stretch")

# --- LOGIN AUTOMÁTICO / RESTAURACIÓN ---
auto_login_done = False
if st.session_state["cl"] is None:
    try:
        st.session_state["cl"] = login(IG_USERNAME, IG_PASSWORD)
        st.success(f"✅ Sesión restaurada automáticamente como {IG_USERNAME}")
        auto_login_done = True
    except Exception as e:
        st.warning("🔐 No hay sesión activa. Inicia sesión para continuar.")
        st.session_state["cl"] = None

# --- MOSTRAR BOTÓN DE LOGIN SI NO HAY SESIÓN ---
if st.session_state["cl"] is None:
    if st.button("🔑 Iniciar sesión en Instagram"):
        with st.spinner("Conectando con Instagram..."):
            try:
                cl = login(IG_USERNAME, IG_PASSWORD)
                st.session_state["cl"] = cl
                st.success(f"✅ Sesión iniciada correctamente como {IG_USERNAME}")
                st.rerun()  # 🔁 Refresca la app tras el login
            except Exception as e:
                st.error(f"❌ Error al iniciar sesión: {e}")

# --- OBTENER LIKES ---
if st.session_state["cl"]:
    st.subheader("📸 Obtener Likes de una publicación")
    url = st.text_input("Introduce la URL del post de Instagram:")

    st.caption(
        "📊 *Instagram impone límites de visibilidad en los likes:*\n\n"
        "• En publicaciones **de otras cuentas**, solo se pueden obtener aproximadamente **100–120 likes visibles**.\n"
        "• Si el post **es de tu propia cuenta**, podrás ver más **likes**.\n\n"
        "💡 *Este límite es propio de Instagram, no de la herramienta.*"
    )

    if st.button("📊 Sacar información de likes"):
        if not url:
            st.warning("⚠️ Debes introducir la URL del post.")
        elif "/p/" not in url:
            st.error("⚠️ Solo se admiten posts del tipo https://www.instagram.com/p/<código>/")
        else:
            try:
                # 🧠 Cargar progreso guardado de ese post
                current_offset, total_saved_likes = get_post_progress(url)

                # Obtener información del post para conocer el total real de likes
                media_pk = extract_media_pk(st.session_state["cl"], url)
                st.session_state["cl"] = ensure_login(st.session_state["cl"], IG_USERNAME, IG_PASSWORD)

                try:
                    media_info = st.session_state["cl"].media_info(media_pk)
                    total_likes = getattr(media_info, "like_count", 0)
                except Exception:
                    total_likes = 0

                # Evitar reiniciar si ya llegaste al final del post
                if total_likes > 0 and current_offset >= total_likes:
                    st.warning("✅ Ya alcanzaste el límite máximo de likes visibles para este post.")
                    st.stop()

                start_offset = current_offset
                end_offset = start_offset + num_likes
                st.info(f"📡 Obteniendo likes desde {start_offset} hasta {end_offset}...")

                media_pk = extract_media_pk(st.session_state["cl"], url)
                st.session_state["cl"] = ensure_login(st.session_state["cl"], IG_USERNAME, IG_PASSWORD)

                # --- BARRA DE PROGRESO ---
                progress_text = st.empty()
                progress_bar = st.progress(0)

                result = get_likers(
                    st.session_state["cl"],
                    media_pk,
                    batch_size=num_likes,
                    offset=current_offset
                )

                likers = result["likers"]
                total = len(likers)

                for i, user in enumerate(likers):
                    progress = int((i + 1) / total * 100)
                    progress_bar.progress(progress)
                    progress_text.text(f"Procesando usuario {i + 1}/{total}...")

                    # 💤 Espera aleatoria para no parecer bot
                    time.sleep(random.uniform(3.5, 5.5))

                progress_bar.progress(100)
                progress_text.text("✅ Lote completado")

                df = pd.DataFrame(likers)
                st.session_state["likers_data"].extend(likers)
                st.dataframe(df, width="stretch")

                # 💾 Guardar progreso nuevo (solo si hay datos)
                if len(likers) > 0:
                    # Si todavía hay más likes disponibles
                    if result["has_more"] and result["next_offset"] is not None:
                        new_offset = result["next_offset"]
                        st.info(f"📈 Progreso guardado: {new_offset} / {result['media_like_count']}")
                    else:
                        # Llegamos al final → guardamos el total real para marcar completado
                        new_offset = result.get("media_like_count", current_offset)
                        st.success("✅ Todos los likes de este post han sido procesados (límite alcanzado).")

                    # ⚠️ Guardar progreso solo si cambia realmente
                    if new_offset > current_offset:
                        save_post_progress(url, new_offset, total_likes)
                    else:
                        st.info("ℹ️ No se actualizó el progreso porque ya se había alcanzado el límite.")

                    st.session_state["last_progress"] = {
                        "url": url,
                        "offset": new_offset,
                        "count": len(likers),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

                else:
                    # Si el lote no devuelve nada nuevo
                    st.warning(
                        "⚠️ No se encontraron nuevos usuarios en este lote. "
                        "Es posible que ya hayas alcanzado el límite de likes visibles para este post."
                    )

            except Exception as e:
                error_text = str(e).lower()
                # 🚨 Caso 1: challenge o login
                if "conecta a instagram de nuevo" in error_text or "login_required" in error_text or "challenge_required" in error_text:
                    st.warning("🔐 Conecta a Instagram de nuevo para confirmar tu identidad. "
                               "Abre tu aplicación de Instagram, aprueba el acceso, y vuelve aquí para continuar.")
                    st.session_state["cl"] = None
                    time.sleep(3)
                    st.rerun()  # 🔁 Vuelve a dibujar la app mostrando el botón de inicio
                # 🚨 Caso 2: otros errores normales
                else:
                    st.error(f"❌ Error al obtener información: {e}")

    # --- GUARDAR EN BASE DE DATOS ---
    if st.session_state["likers_data"]:
        st.subheader("💾 Guardar datos en base de datos")

        if st.button("💾 Guardar likes en base de datos"):
            with st.spinner("Guardando información en la base de datos..."):
                try:
                    added = save_likers(st.session_state["likers_data"])
                    st.success(f"✅ Se guardaron {added} nuevos usuarios en la base de datos.")
                except Exception as e:
                    st.error(f"❌ Error al guardar en base de datos: {e}")

        # --- ENVÍO DE MENSAJES ---
        st.subheader("📨 Enviar mensajes automáticos con IA")
        only_public = True

        if st.button("🤖 Generar mensajes con IA"):
            with st.spinner("Generando mensajes personalizados..."):
                pending_users = get_pending(limit=num_messages, only_public=only_public)

                if not pending_users:
                    st.info("✅ No hay usuarios pendientes para contactar.")
                else:
                    generated_messages = []
                    total = len(pending_users)
                    progress = st.progress(0)

                    for i, (username, full_name, pk) in enumerate(pending_users):
                        try:
                            conn = sqlite3.connect("insta_bot.sqlite")
                            cur = conn.cursor()
                            cur.execute("SELECT language FROM contacts WHERE username=?", (username,))
                            row = cur.fetchone()
                            conn.close()
                            lang = row[0] if row and row[0] else "es"

                            message = generate_dm(
                                full_name or username,
                                lang,
                                st.session_state["custom_template_es"],
                                st.session_state["custom_template_en"]
                            )
                            generated_messages.append({
                                "username": username,
                                "full_name": full_name,
                                "pk": pk,
                                "language": lang,
                                "message": message
                            })

                            progress.progress(int((i + 1) / total * 100))
                            time.sleep(random.uniform(3, 5))
                        except Exception as e:
                            st.write(f"⚠️ Error generando mensaje para {username}: {e}")

                    st.session_state["generated_messages"] = generated_messages
                    st.success(f"✅ Se generaron {len(generated_messages)} mensajes con IA.")
                    st.write("### 📄 Vista previa de mensajes generados")

                    for msg in generated_messages:
                        st.markdown(f"**👤 {msg['username']}** ({msg['language']})")
                        st.text_area(f"Mensaje para {msg['username']}", msg["message"], height=100, key=f"preview_{msg['username']}")

        # --- ENVIAR MENSAJES ---
        from datetime import datetime
        from db import get_last_send_ts, update_last_send_ts

        if "generated_messages" in st.session_state and st.session_state["generated_messages"]:
            st.subheader("🚀 Enviar todos los mensajes")

            # 🕒 Control de tiempo (cooldown de 10 minutos)
            cooldown_minutes = 10
            cooldown_key = "global_send"  # puedes usar "global_send" o un identificador por post
            last_ts = get_last_send_ts(cooldown_key)
            now = int(time.time())
            remaining = last_ts + cooldown_minutes * 60 - now

            if remaining > 0:
                mins = remaining // 60
                secs = remaining % 60
                st.warning(f"⏳ Espera {mins} min {secs} s antes de volver a enviar mensajes.")
            else:
                if st.button("🚀 Enviar todos los mensajes"):
                    with st.spinner("Enviando mensajes..."):
                        sent = 0
                        total = len(st.session_state["generated_messages"])
                        progress = st.progress(0)

                        for i, msg in enumerate(st.session_state["generated_messages"]):
                            username = msg["username"]
                            user_id = msg["pk"]

                            try:
                                # 🧠 Verifica sesión activa antes de cada envío
                                st.session_state["cl"] = ensure_login(st.session_state["cl"], IG_USERNAME, IG_PASSWORD)

                                # 🚀 Envía el mensaje
                                st.session_state["cl"].direct_send(msg["message"], user_ids=[user_id])
                                mark_contacted(username)
                                sent += 1
                                st.write(f"✅ Mensaje enviado a **{username}** (ID: {user_id})")

                            except RateLimitError:
                                st.error("⚠️ Límite de Instagram alcanzado. Espera antes de continuar.")
                                break

                            except ClientError as e:
                                err_text = str(e).lower()
                                if "not authorized" in err_text:
                                    st.write(f"🚫 No autorizado para enviar mensaje a {username}.")
                                    continue
                                elif "login_required" in err_text or "challenge_required" in err_text:
                                    st.warning(
                                        "🔐 Conecta a Instagram de nuevo para confirmar tu identidad. "
                                        "Abre la app oficial, aprueba el acceso, y vuelve aquí para continuar."
                                    )
                                    st.session_state["cl"] = None
                                    time.sleep(3)
                                    st.rerun()
                                    continue
                                else:
                                    st.write(f"⚠️ Error con {username}: {e}")
                                    continue

                            except Exception as e:
                                err_text = str(e).lower()
                                if "login_required" in err_text or "challenge_required" in err_text:
                                    st.warning(
                                        "🔐 Conecta a Instagram de nuevo para confirmar tu identidad. "
                                        "Abre tu aplicación de Instagram, aprueba el acceso, y vuelve aquí para continuar."
                                    )
                                    st.session_state["cl"] = None
                                    time.sleep(3)
                                    st.rerun()
                                    continue
                                st.write(f"⚠️ Error inesperado con {username}: {e}")
                                continue

                            # 📊 Actualiza la barra de progreso
                            progress.progress(int((i + 1) / total * 100))
                            time.sleep(random.uniform(6, 9))

                        st.success(f"📨 Se enviaron {sent} mensajes correctamente.")
                        st.session_state.pop("generated_messages", None)

                        # 💾 Guarda timestamp del último envío (persistente)
                        update_last_send_ts(cooldown_key)
                        st.info(f"🕒 Envíos bloqueados por {cooldown_minutes} minutos.")

