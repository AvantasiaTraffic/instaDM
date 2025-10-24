from instagrapi import Client
from langdetect import detect, DetectorFactory
import random
import os, re, time, json, uuid

DetectorFactory.seed = 0

# ------------------------------
# 🔐 ARCHIVOS DE SESIÓN / COOKIES
# ------------------------------
def session_file(username):
    safe_username = username.replace("@", "_").replace(".", "_")
    return f"session_{safe_username}.json"

def cookies_file(username):
    safe_username = username.replace("@", "_").replace(".", "_")
    return f"cookies_{safe_username}.json"


# ------------------------------
# 🧠 LOGIN PRINCIPAL (con cookies y device fijos)
# ------------------------------
def login(username, password):
    """
    Login persistente con prioridad:
    1️⃣ Cookies del navegador (si existen)
    2️⃣ Sesión JSON de instagrapi
    3️⃣ Login tradicional con device settings fijos
    """
    cookies_path = cookies_file(username)
    session_path = session_file(username)

    # --- Crear nuevo cliente limpio ---
    client = Client()

    # ------------------------------
    # 1️⃣ Intentar restaurar cookies
    # ------------------------------
    if os.path.exists(cookies_path):
        try:
            with open(cookies_path, "r") as f:
                cookies = json.load(f)
            client.set_settings({"cookies": cookies})
            client.get_timeline_feed()
            print(f"✅ Sesión restaurada desde cookies ({cookies_path})")
            return client
        except Exception as e:
            print(f"⚠️ Cookies inválidas ({e}). Probando sesión JSON...")

    # ------------------------------
    # 2️⃣ Intentar restaurar sesión JSON
    # ------------------------------
    if os.path.exists(session_path):
        try:
            client.load_settings(session_path)
            client.get_timeline_feed()
            print(f"✅ Sesión válida restaurada desde {session_path}")
            return client
        except Exception as e:
            print(f"⚠️ Sesión inválida ({e}). Eliminando archivo...")
            try:
                os.remove(session_path)
            except:
                pass
            time.sleep(2)

    # ------------------------------
    # 3️⃣ Login limpio (con device fijo)
    # ------------------------------
    print("🔁 Creando nueva sesión con device fijo...")

    fixed_device = {
        "manufacturer": "Samsung",
        "device": "SM-G973F",
        "model": "SM-G973F",
        "android_version": 28,
        "android_release": "9.0",
        "dpi": "480dpi",
        "resolution": "1080x1920",
        "cpu": "qcom",
        "version_code": "314665256",
        "app_version": "269.0.0.18.75",
    }

    fixed_ids = {
        "uuid": "d9f3c0d1-1d2f-4f4b-86b3-ae1b91a6a001",
        "phone_id": "bd0e9f01-6a1c-4a4a-8a4f-ffd733002888",
        "device_id": "android-38c9b4e47f92a123",
        "adid": "17d45662-4a9f-4a3a-bb9a-2b38b77a4413",
        "android_device_id": "25bd27bb-a69a-4b8a-8811-e391fb07a5fa",
    }

    client.set_settings({
        "uuids": fixed_ids,
        "device_settings": fixed_device,
    })

    # 🔐 Login real
    client.login(username, password)
    print("✅ Login exitoso")

    # ⚡ Fuerza peticiones que generan actividad
    try:
        client.get_timeline_feed()
        client.user_info_by_username(username)
    except Exception:
        pass

    # ------------------------------
    # 💾 Guardar sesión + cookies simuladas
    # ------------------------------
    settings = client.get_settings()
    auth = settings.get("authorization_data", {})

    # Simular cookies desde authorization_data
    cookies = {
        "sessionid": auth.get("sessionid"),
        "ds_user_id": auth.get("ds_user_id"),
    }

    # Guardar archivos
    client.dump_settings(session_path)
    with open(cookies_path, "w") as f:
        json.dump(cookies, f)

    print(f"💾 Sesión guardada en {session_path}")
    print(f"🍪 Cookies simuladas guardadas en {cookies_path}: {len(cookies)} claves")

    return client


# ------------------------------
# 🧭 COMPROBAR SESIÓN ACTIVA
# ------------------------------
def ensure_login(client, username, password):
    """Verifica si la sesión sigue activa; si no, la regenera completamente."""
    try:
        client.get_timeline_feed()
        return client
    except Exception as e:
        if "login_required" in str(e).lower():
            print("🔐 Sesión expirada. Reautenticando completamente...")
            session_path = session_file(username)
            if os.path.exists(session_path):
                try:
                    os.remove(session_path)
                    print(f"🗑️ Sesión anterior eliminada: {session_path}")
                except:
                    pass
            time.sleep(2)
            new_client = login(username, password)
            return new_client
        else:
            raise


# ------------------------------
# 🔍 EXTRAER MEDIA_PK DESDE URL
# ------------------------------
def extract_media_pk(client, url: str):
    """Obtiene el media_pk compatible con cualquier versión de instagrapi."""
    try:
        if hasattr(client, "media_pk_from_url"):
            return client.media_pk_from_url(url)
    except Exception:
        pass

    m = re.search(r"/p/([^/?#]+)/", url)
    if not m:
        raise Exception("URL inválida: se espera https://www.instagram.com/p/<shortcode>/")
    shortcode = m.group(1)

    try:
        if hasattr(client, "media_info_by_url"):
            media = client.media_info_by_url(url)
            if media and getattr(media, "pk", None):
                return media.pk
    except Exception:
        pass

    for attr in ("media_pk_from_code", "media_pk_from_shortcode"):
        try:
            if hasattr(client, attr):
                fn = getattr(client, attr)
                pk = fn(shortcode)
                if pk:
                    return pk
        except Exception:
            pass

    raise Exception("No se pudo resolver el media_pk desde la URL con los métodos disponibles.")


# ------------------------------
# ❤️ OBTENER LIKERS (CON PAGINACIÓN)
# ------------------------------
def get_likers(client, media_pk, batch_size=10, offset=0):
    """
    Obtiene 'batch_size' usuarios que dieron like, desde 'offset'.
    Filtra privados y detecta idioma.
    """
    try:
        media_info = client.media_info(media_pk)
        caption_text = getattr(media_info.caption, "text", "")
        owner_username = getattr(media_info.user, "username", "unknown")
        like_count = getattr(media_info, "like_count", 0)
    except Exception:
        caption_text, owner_username, like_count = "", "unknown", 0

    try:
        likers = client.media_likers(media_pk)
    except Exception as e:
        raise Exception(f"Error al obtener likers: {e}")

    likers_batch = likers[offset : offset + batch_size]
    data = []

    for u in likers_batch:
        if u.is_private:
            print(f"🚫 {u.username} es privado. Saltando...")
            continue

        try:
            user_full = client.user_info(u.pk)
            try:
                lang = detect(user_full.biography) if user_full.biography else "english"
            except:
                lang = "english"

            data.append({
                "pk": u.pk,
                "username": u.username,
                "full_name": u.full_name,
                "is_private": u.is_private,
                "profile_pic_url": u.profile_pic_url,
                "is_verified": user_full.is_verified,
                "language": lang,
            })
        except Exception as e:
            err_text = str(e).lower()

            if "challenge_required" in err_text or "login_required" in err_text:
                print("🔐 Conecta a Instagram de nuevo para confirmar tu identidad y continuar.")
                # Detenemos el proceso si la sesión ya no es válida
                raise Exception("🔐 Conecta a Instagram de nuevo para confirmar tu identidad y continuar.")

            elif "not authorized" in err_text:
                print(f"🚫 No autorizado a ver el perfil de {u.username}.")
                continue

            else:
                print(f"⚠️ Error con usuario {u.username}: {e}")
                continue

        time.sleep(random.uniform(2, 4))

    has_more = offset + batch_size < len(likers)
    return {
        "media_caption": caption_text,
        "media_owner": owner_username,
        "media_like_count": like_count,
        "likers": data,
        "has_more": has_more,
        "next_offset": offset + batch_size if has_more else None
    }
