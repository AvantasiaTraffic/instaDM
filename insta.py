from instagrapi import Client
from langdetect import detect, DetectorFactory
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
    Inicia sesión con prioridad:
    1️⃣ Cookies del navegador (si existen)
    2️⃣ Sesión JSON de instagrapi
    3️⃣ Login tradicional con device settings estables
    """
    cookies_path = cookies_file(username)
    session_path = session_file(username)

    # --- Crear cliente limpio cada vez ---
    client = Client()

    # 1️⃣ Intentar restaurar sesión desde cookies reales
    if os.path.exists(cookies_path):
        try:
            with open(cookies_path, "r") as f:
                cookies = json.load(f)
            client.set_settings({"cookies": cookies})
            client.get_timeline_feed()
            print(f"✅ Sesión restaurada desde cookies ({cookies_path})")
            return client
        except Exception as e:
            print(f"⚠️ Cookies inválidas ({e}). Intentando siguiente método...")

    # 2️⃣ Intentar restaurar sesión desde JSON
    if os.path.exists(session_path):
        try:
            client.load_settings(session_path)
            client.get_timeline_feed()
            print(f"✅ Sesión válida restaurada desde {session_path}")
            return client
        except Exception as e:
            print(f"⚠️ Sesión inválida ({e}). Eliminando archivo y regenerando...")
            try:
                os.remove(session_path)
            except:
                pass
            time.sleep(2)
            client = Client()

    # 3️⃣ Login tradicional si no hay sesión válida
    try:
        print("🔁 Creando nueva sesión con device fijo...")
        client.login(username, password)

        # ⚙️ Device Settings fijos (para evitar "nuevo dispositivo")
        settings = client.get_settings() or {}
        ds = settings.get("device_settings", {})

        ds.setdefault("manufacturer", "Samsung")
        ds.setdefault("device", "SM-G973F")
        ds.setdefault("model", "SM-G973F")
        ds.setdefault("android_version", 28)
        ds.setdefault("android_release", "9")

        settings.setdefault("uuid", settings.get("uuid", str(uuid.uuid4())))
        ds.setdefault("device_id", ds.get("device_id", str(uuid.uuid4())))
        ds.setdefault("phone_id", ds.get("phone_id", str(uuid.uuid4())))
        ds.setdefault("adid", ds.get("adid", str(uuid.uuid4())))
        ds.setdefault("android_device_id", ds.get("android_device_id", str(uuid.uuid4())))

        settings["device_settings"] = ds
        client.set_settings(settings)

        # 💾 Guardar sesión y cookies
        client.dump_settings(session_path)
        cookies = client.get_settings().get("cookies")
        if cookies:
            with open(cookies_path, "w") as f:
                json.dump(cookies, f)
            print(f"🍪 Cookies guardadas en {cookies_path}")

        print(f"💾 Nueva sesión guardada en {session_path}")
        return client

    except Exception as e:
        if "challenge_required" in str(e):
            print("⚠️ Instagram requiere verificación (challenge).")
            try:
                challenge = client.challenge_resolve()
                if not challenge:
                    code = input("Introduce el código recibido por email/SMS: ")
                    client.challenge_code_handler(code)
                    client.dump_settings(session_path)
                    print("✅ Challenge completado y sesión guardada.")
                    return client
            except Exception as e2:
                raise Exception(f"Challenge no completado: {e2}")
        else:
            raise Exception(f"❌ Error al iniciar sesión: {e}")


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
            if "Not authorized" in str(e):
                print(f"🚫 No autorizado a ver el perfil de {u.username}.")
                continue
            print(f"⚠️ Error con usuario {u.username}: {e}")
            continue

        time.sleep(1)

    has_more = offset + batch_size < len(likers)
    return {
        "media_caption": caption_text,
        "media_owner": owner_username,
        "media_like_count": like_count,
        "likers": data,
        "has_more": has_more,
        "next_offset": offset + batch_size if has_more else None
    }
